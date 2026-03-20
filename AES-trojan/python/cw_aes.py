#!/usr/bin/env python3
"""
ChipWhisperer Husky AES-128 Communication & Power Trace Capture Script.

This script:
  - Connects to the ChipWhisperer Husky and CW312-A35 target
  - Sends plaintext/key to the FPGA for AES-128 ECB encryption/decryption
  - Captures power traces from the Husky during encryption
  - Verifies results against PyCryptodome software implementation
  - Saves all data (plaintext, key, ciphertext, power traces) to .mat and .json

Usage:
  # Encrypt with default NIST test vectors
  python3 cw_aes.py encrypt

  # Encrypt with custom key and plaintext
  python3 cw_aes.py encrypt --key 2b7e151628aed2a6abf7158809cf4f3c \\
                             --data 6bc1bee22e409f96e93d7e117393172a

  # Capture N traces with random plaintexts
  python3 cw_aes.py encrypt --num-traces 100 --random

  # Configure Husky sampling
  python3 cw_aes.py encrypt --sample-rate 20e6 --num-samples 5000 --random --num-traces 50

  # Decrypt
  python3 cw_aes.py decrypt --key 2b7e151628aed2a6abf7158809cf4f3c \\
                             --data 3ad77bb40d7a3660a89ecaf32466ef97

  # Save to specific output files
  python3 cw_aes.py encrypt --output-mat traces.mat --output-json traces.json --random --num-traces 10
"""

import argparse
import json
import os
import sys
import time
import datetime
import numpy as np

try:
    import chipwhisperer as cw
except ImportError:
    print("ERROR: chipwhisperer package not installed. Install with: pip install chipwhisperer")
    sys.exit(1)

try:
    from Crypto.Cipher import AES as AES_SW
except ImportError:
    try:
        from Cryptodome.Cipher import AES as AES_SW
    except ImportError:
        print("ERROR: pycryptodome not installed. Install with: pip install pycryptodome")
        sys.exit(1)

try:
    import scipy.io as sio
except ImportError:
    print("ERROR: scipy not installed. Install with: pip install scipy")
    sys.exit(1)


def software_aes_encrypt(key_bytes, pt_bytes):
    """AES-128 ECB encryption using PyCryptodome."""
    cipher = AES_SW.new(key_bytes, AES_SW.MODE_ECB)
    return cipher.encrypt(pt_bytes)


def software_aes_decrypt(key_bytes, ct_bytes):
    """AES-128 ECB decryption using PyCryptodome."""
    cipher = AES_SW.new(key_bytes, AES_SW.MODE_ECB)
    return cipher.decrypt(ct_bytes)


def connect_husky(sn=None, bitstream=None, freq=7_370_000):
    """Connect to ChipWhisperer Husky and CW312T-A35 target via SS2."""
    from chipwhisperer.hardware.naeusb.programmer_targetfpga import CW312T_XC7A35T
    from chipwhisperer.capture.targets.SimpleSerial2 import SimpleSerial2
    from chipwhisperer.capture.targets.CW305 import SS2_CW305_NoPll

    print("[*] Connecting to ChipWhisperer Husky...")
    scope = cw.scope(sn=sn) if sn else cw.scope()
    print(f"    Connected: {scope.get_name()} (FW: {scope.fw_version_str})")

    # Configure clock generator
    scope.clock.clkgen_freq = freq
    scope.io.hs2 = None  # disable during programming
    time.sleep(0.1)

    # Program FPGA if bitstream provided
    if bitstream:
        print(f"[*] Programming FPGA: {bitstream}")
        fpga = CW312T_XC7A35T(scope)
        fpga.program(bitstream, sck_speed=10e6)
        print("    FPGA programmed.")

    # Enable clock and reset
    scope.io.hs2 = 'clkgen'
    time.sleep(0.3)
    scope.io.nrst = 'low'
    time.sleep(0.05)
    scope.io.nrst = 'high'
    time.sleep(0.5)

    # CRITICAL: TIO1/TIO2 swapped for CW312T-A35 SS2
    scope.io.tio1 = 'serial_rx'
    scope.io.tio2 = 'serial_tx'
    time.sleep(0.1)

    # Connect SS2 and create CW305 target
    print("[*] Connecting SS2 target...")
    ss2 = SimpleSerial2()
    ss2.con(scope)
    target = cw.targets.CW305()
    target.platform = 'ss2'
    target.ss2 = ss2
    target._naeusb = None
    target.connectStatus = True
    target.pll = SS2_CW305_NoPll()
    target.bytecount_size = 8

    # Verify connection
    ident = target.fpga_read(0x04, 1)
    print(f"    IDENTIFY=0x{ident[0]:02x}, Target connected.")

    return scope, target


def configure_husky(scope, target, args):
    """Configure Husky scope settings for power trace capture."""
    print("[*] Configuring Husky settings...")

    # Clock (already set in connect_husky)
    print(f"    Clock frequency: {scope.clock.clkgen_freq} Hz")

    # Trigger configuration: IO4 carries tio_trigger from FPGA (busy signal)
    scope.trigger.triggers = "tio4"
    scope.io.tio4 = "high_z"  # input from target
    print(f"    Trigger source: TIO4 (AES busy)")

    # ADC / sampling configuration
    # Note: scope.clock.adc_freq is read-only on Husky; set adc_mul instead
    if args.sample_rate:
        desired_mul = round(args.sample_rate / scope.clock.clkgen_freq)
        desired_mul = max(1, desired_mul)
        scope.clock.adc_mul = desired_mul
        print(f"    ADC multiplier: {desired_mul}x (from --sample-rate {args.sample_rate:.0f})")
    else:
        scope.clock.adc_mul = args.adc_mul
        print(f"    ADC multiplier: {scope.clock.adc_mul}x")
    print(f"    ADC sample rate: {scope.clock.adc_freq} Hz")

    scope.adc.samples = args.num_samples
    print(f"    Samples per trace: {scope.adc.samples}")

    scope.adc.presamples = args.pre_samples
    print(f"    Pre-trigger samples: {scope.adc.presamples}")

    scope.adc.timeout = args.timeout
    print(f"    Trigger timeout: {scope.adc.timeout} ms")

    scope.gain.db = args.gain_db
    print(f"    Gain: {scope.gain.db} dB")

    print("    Configuration complete.")
    return scope, target


def capture_trace(scope, target, key_bytes, data_bytes, operation="encrypt"):
    """
    Send key + data to target via CW305 registers, capture power trace, return result.

    Register map (cw305_aes_defines.v):
      0x0a: REG_CRYPT_KEY (16 bytes)
      0x06: REG_CRYPT_TEXTIN (16 bytes)
      0x05: REG_CRYPT_GO (write 1 to start, read for busy status)
      0x09: REG_CRYPT_CIPHEROUT (16 bytes)

    Returns:
        result_bytes: 16-byte ciphertext from FPGA
        trace: numpy array of power samples
    """
    # Load key and plaintext into registers
    target.fpga_write(0x0a, list(key_bytes))
    target.fpga_write(0x06, list(data_bytes))

    # Arm the scope for capture (trigger on IO4 = AES busy)
    scope.arm()

    # Trigger encryption
    target.fpga_write(0x05, [0x01])

    # Wait for capture to complete
    ret = scope.capture()
    if ret:
        print("    WARNING: Trigger timeout — no trigger detected")
        # Still try to read result even if trigger missed
        time.sleep(0.1)

    # Wait for AES to complete
    for _ in range(100):
        busy = target.fpga_read(0x05, 1)
        if busy[0] == 0:
            break
        time.sleep(0.01)

    # Read ciphertext
    ct = target.fpga_read(0x09, 16)
    response = bytes(ct) if ct else None

    # Get power trace
    trace = scope.get_last_trace()

    return response, trace


def run_encryption(scope, target, args):
    """Run encryption operation(s) and collect data."""
    key_bytes = bytes.fromhex(args.key)
    num_traces = args.num_traces

    # Storage
    plaintexts = []
    ciphertexts_hw = []
    ciphertexts_sw = []
    traces = []
    mismatches = 0

    print(f"\n[*] Running AES-128 ECB encryption ({num_traces} trace(s))...")
    print(f"    Key: {args.key}")

    for i in range(num_traces):
        # Generate or use provided plaintext
        if args.random or (args.data is None and num_traces > 1):
            pt_bytes = os.urandom(16)
        elif args.data:
            pt_bytes = bytes.fromhex(args.data)
        else:
            # Default NIST test vector
            pt_bytes = bytes.fromhex("6bc1bee22e409f96e93d7e117393172a")

        # Software reference
        ct_sw = software_aes_encrypt(key_bytes, pt_bytes)

        # Hardware encryption + trace capture
        ct_hw, trace = capture_trace(scope, target, key_bytes, pt_bytes, "encrypt")

        if ct_hw is None or trace is None:
            print(f"    [{i+1}/{num_traces}] FAILED (no response)")
            continue

        # Verify
        match = (ct_hw == ct_sw)
        if not match:
            mismatches += 1

        plaintexts.append(pt_bytes)
        ciphertexts_hw.append(ct_hw)
        ciphertexts_sw.append(ct_sw)
        traces.append(trace)

        status = "\033[32mOK\033[0m" if match else "\033[31mMISMATCH\033[0m"
        print(f"    [{i+1:>{len(str(num_traces))}}/{num_traces}] PT={pt_bytes.hex()} CT_HW={ct_hw.hex()} CT_SW={ct_sw.hex()} [{status}]")

    return plaintexts, ciphertexts_hw, ciphertexts_sw, traces, mismatches


def run_decryption(scope, target, args):
    """
    Run decryption operation(s) and collect data.
    Note: The FPGA only implements encryption. Decryption is done in software.
    The power traces are still captured during the encrypt operation used internally.
    """
    key_bytes = bytes.fromhex(args.key)
    num_traces = args.num_traces

    ciphertexts = []
    plaintexts_sw = []
    traces = []

    print(f"\n[*] Running AES-128 ECB decryption ({num_traces} trace(s))...")
    print(f"    Key: {args.key}")
    print("    Note: FPGA performs encryption; decryption is verified in software.")

    for i in range(num_traces):
        if args.random or (args.data is None and num_traces > 1):
            ct_bytes = os.urandom(16)
        elif args.data:
            ct_bytes = bytes.fromhex(args.data)
        else:
            ct_bytes = bytes.fromhex("3ad77bb40d7a3660a89ecaf32466ef97")

        # Software decryption
        pt_sw = software_aes_decrypt(key_bytes, ct_bytes)

        # We re-encrypt the software-decrypted plaintext on HW to verify
        ct_hw, trace = capture_trace(scope, target, key_bytes, pt_sw, "encrypt")

        ciphertexts.append(ct_bytes)
        plaintexts_sw.append(pt_sw)
        if trace is not None:
            traces.append(trace)

        if ct_hw is not None:
            match = (ct_hw == ct_bytes)
            status = "OK" if match else "MISMATCH"
        else:
            status = "NO_RESP"

        if num_traces <= 10 or (i + 1) % max(1, num_traces // 10) == 0:
            print(f"    [{i+1}/{num_traces}] CT={ct_bytes.hex()} PT_SW={pt_sw.hex()} [{status}]")

    return ciphertexts, plaintexts_sw, [], traces, 0


def save_results(args, operation, plaintexts, ciphertexts_hw, ciphertexts_sw, traces, mismatches):
    """Save results to .mat and .json files."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    os.makedirs(data_dir, exist_ok=True)

    # Default filenames
    mat_file = args.output_mat or os.path.join(data_dir, f"aes_{operation}_{timestamp}.mat")
    json_file = args.output_json or os.path.join(data_dir, f"aes_{operation}_{timestamp}.json")

    num_collected = len(plaintexts)
    if num_collected == 0:
        print("\n[!] No data collected — nothing to save.")
        return

    # Convert to numpy arrays
    pt_array = np.array([list(pt) for pt in plaintexts], dtype=np.uint8)
    ct_hw_array = np.array([list(ct) for ct in ciphertexts_hw], dtype=np.uint8) if ciphertexts_hw else np.array([])
    ct_sw_array = np.array([list(ct) for ct in ciphertexts_sw], dtype=np.uint8) if ciphertexts_sw else np.array([])
    traces_array = np.array(traces, dtype=np.float64) if traces else np.array([])
    key_array = np.array(list(bytes.fromhex(args.key)), dtype=np.uint8)

    # ---- Save .mat file ----
    mat_data = {
        "operation": operation,
        "key": key_array,
        "plaintexts": pt_array,
        "ciphertexts_hw": ct_hw_array,
        "ciphertexts_sw": ct_sw_array,
        "traces": traces_array,
        "num_traces": num_collected,
        "num_samples": args.num_samples,
        "sample_rate": args.sample_rate if args.sample_rate else 0,
        "clk_freq": args.clk_freq,
        "gain_db": args.gain_db,
        "mismatches": mismatches,
        "timestamp": timestamp,
    }
    sio.savemat(mat_file, mat_data)
    print(f"\n[*] Saved .mat file: {mat_file}")

    # ---- Save .json file ----
    json_data = {
        "operation": operation,
        "key": args.key,
        "timestamp": timestamp,
        "num_traces": num_collected,
        "num_samples": args.num_samples,
        "sample_rate": args.sample_rate if args.sample_rate else "auto",
        "clk_freq": args.clk_freq,
        "gain_db": args.gain_db,
        "protocol": "SS2",
        "mismatches": mismatches,
        "data": [],
    }
    for i in range(num_collected):
        entry = {
            "index": i,
            "plaintext": plaintexts[i].hex(),
        }
        if ciphertexts_hw and i < len(ciphertexts_hw):
            entry["ciphertext_hw"] = ciphertexts_hw[i].hex()
        if ciphertexts_sw and i < len(ciphertexts_sw):
            entry["ciphertext_sw"] = ciphertexts_sw[i].hex()
        if ciphertexts_hw and ciphertexts_sw and i < len(ciphertexts_hw) and i < len(ciphertexts_sw):
            entry["match"] = ciphertexts_hw[i] == ciphertexts_sw[i]
        json_data["data"].append(entry)

    # Note: power traces are NOT stored in JSON (too large); they are in the .mat file.
    json_data["note"] = "Power traces are stored in the .mat file only (too large for JSON)."

    with open(json_file, "w") as f:
        json.dump(json_data, f, indent=2)
    print(f"[*] Saved .json file: {json_file}")

    # Summary
    print(f"\n{'='*60}")
    print(f"  Summary")
    print(f"{'='*60}")
    print(f"  Operation:      {operation}")
    print(f"  Traces:         {num_collected}")
    print(f"  Mismatches:     {mismatches}")
    if traces:
        print(f"  Trace shape:    {traces_array.shape}")
    print(f"  .mat file:      {mat_file}")
    print(f"  .json file:     {json_file}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description="AES-128 ECB communication & power trace capture via ChipWhisperer Husky",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s encrypt
  %(prog)s encrypt --key 00112233445566778899aabbccddeeff --data 00000000000000000000000000000000
  %(prog)s encrypt --random --num-traces 100 --num-samples 5000
  %(prog)s decrypt --key 2b7e151628aed2a6abf7158809cf4f3c --data 3ad77bb40d7a3660a89ecaf32466ef97
        """,
    )

    # Positional: operation
    parser.add_argument(
        "operation",
        choices=["encrypt", "decrypt"],
        help="Operation to perform: encrypt or decrypt",
    )

    # Data arguments
    parser.add_argument(
        "--key",
        default="2b7e151628aed2a6abf7158809cf4f3c",
        help="128-bit key as 32 hex characters (default: NIST test vector key)",
    )
    parser.add_argument(
        "--data",
        default=None,
        help="128-bit plaintext (encrypt) or ciphertext (decrypt) as 32 hex chars",
    )
    parser.add_argument(
        "--random",
        action="store_true",
        help="Use random plaintext/ciphertext for each trace",
    )
    parser.add_argument(
        "--num-traces",
        type=int,
        default=1,
        help="Number of traces to capture (default: 1)",
    )

    # Husky configuration
    parser.add_argument(
        "--clk-freq",
        type=int,
        default=7_370_000,
        help="Target clock frequency in Hz (default: 7370000)",
    )
    parser.add_argument(
        "--sample-rate",
        type=float,
        default=None,
        help="Desired ADC sample rate in Hz; sets nearest adc_mul (default: use --adc-mul)",
    )
    parser.add_argument(
        "--adc-mul",
        type=int,
        default=4,
        help="ADC clock multiplier relative to clkgen (default: 4)",
    )
    parser.add_argument(
        "--num-samples",
        type=int,
        default=5000,
        help="Number of ADC samples per trace (default: 5000)",
    )
    parser.add_argument(
        "--pre-samples",
        type=int,
        default=0,
        help="Number of pre-trigger samples (default: 0)",
    )
    parser.add_argument(
        "--gain-db",
        type=float,
        default=25.0,
        help="ADC gain in dB (default: 25.0)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=2000,
        help="Trigger timeout in ms (default: 2000)",
    )
    parser.add_argument(
        "--bitstream",
        default=None,
        help="Path to .bit bitstream file (programs FPGA if provided)",
    )

    # Connection
    parser.add_argument(
        "--sn",
        default=None,
        help="ChipWhisperer Husky serial number (auto-detect if omitted)",
    )

    # Output
    parser.add_argument(
        "--output-mat",
        default=None,
        help="Path for .mat output file (default: auto-generated in data/)",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Path for .json output file (default: auto-generated in data/)",
    )

    args = parser.parse_args()

    # Validate inputs
    if len(args.key) != 32:
        parser.error("Key must be exactly 32 hex characters (128 bits)")
    try:
        bytes.fromhex(args.key)
    except ValueError:
        parser.error("Key must be valid hexadecimal")

    if args.data:
        if len(args.data) != 32:
            parser.error("Data must be exactly 32 hex characters (128 bits)")
        try:
            bytes.fromhex(args.data)
        except ValueError:
            parser.error("Data must be valid hexadecimal")

    # Connect and configure
    scope, target = connect_husky(sn=args.sn, bitstream=args.bitstream, freq=args.clk_freq)
    try:
        configure_husky(scope, target, args)

        # Run operation
        if args.operation == "encrypt":
            plaintexts, ct_hw, ct_sw, traces, mismatches = run_encryption(scope, target, args)
            save_results(args, "encrypt", plaintexts, ct_hw, ct_sw, traces, mismatches)
        else:
            ciphertexts, pt_sw, _, traces, mismatches = run_decryption(scope, target, args)
            save_results(args, "decrypt", pt_sw, ciphertexts, [], traces, mismatches)

    except KeyboardInterrupt:
        print("\n[!] Interrupted by user.")
    except Exception as e:
        print(f"\n[!] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Disconnect
        print("\n[*] Disconnecting...")
        scope.dis()
        print("[*] Done.")


if __name__ == "__main__":
    main()
