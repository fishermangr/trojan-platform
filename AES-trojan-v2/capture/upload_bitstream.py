#!/usr/bin/env python3
"""
Upload bitstream to CW312-A35 (Artix-7 35T) via CW313 carrier + ChipWhisperer Husky.

This script:
  1. Connects to the ChipWhisperer Husky
  2. Configures the clock generator
  3. Programs the CW312-A35 FPGA via SPI (CW312T_XC7A35T programmer)
  4. Enables clock, resets FPGA, configures SS2 serial
  5. Verifies AES-128 against NIST test vectors

Usage:
  python3 upload_bitstream.py --bitstream ../fpga/build/ss2_aes_wrapper.bit
  python3 upload_bitstream.py --bitstream ../fpga/build/ss2_aes_wrapper.bit --freq 7370000
"""

import argparse
import os
import sys
import time


def connect_target(scope, bitstream_path, freq=7_370_000):
    """Program CW312T-A35 and return (scope, target) with SS2 communication ready."""
    from chipwhisperer.hardware.naeusb.programmer_targetfpga import CW312T_XC7A35T
    from chipwhisperer.capture.targets.SimpleSerial2 import SimpleSerial2
    from chipwhisperer.capture.targets.CW305 import SS2_CW305_NoPll
    import chipwhisperer as cw

    # Configure clock generator (before programming)
    scope.clock.clkgen_freq = freq
    scope.io.hs2 = None  # disable HS2 during programming (improves reliability)
    time.sleep(0.1)

    # Program FPGA via SPI
    fpga = CW312T_XC7A35T(scope)
    fpga.program(bitstream_path, sck_speed=10e6)

    # Enable clock output to target
    scope.io.hs2 = 'clkgen'
    time.sleep(0.3)

    # Reset FPGA
    scope.io.nrst = 'low'
    time.sleep(0.05)
    scope.io.nrst = 'high'
    time.sleep(0.5)

    # Configure serial IO (CRITICAL: TIO1/TIO2 are swapped for CW312T-A35 SS2)
    # FPGA txd is on IO1/V10, rxd is on IO2/V11
    # So scope receives on TIO1 and transmits on TIO2
    scope.io.tio1 = 'serial_rx'
    scope.io.tio2 = 'serial_tx'
    time.sleep(0.1)

    # Connect SS2 protocol handler
    ss2 = SimpleSerial2()
    ss2.con(scope)

    # Create CW305 target object for register access
    target = cw.targets.CW305()
    target.platform = 'ss2'
    target.ss2 = ss2
    target._naeusb = None
    target.connectStatus = True
    target.pll = SS2_CW305_NoPll()
    target.bytecount_size = 8

    return target


def verify_aes(target):
    """Run NIST AES-128 test vectors and return True if all pass."""
    vectors = [
        ("2b7e151628aed2a6abf7158809cf4f3c",
         "6bc1bee22e409f96e93d7e117393172a",
         "3ad77bb40d7a3660a89ecaf32466ef97"),
        ("000102030405060708090a0b0c0d0e0f",
         "00112233445566778899aabbccddeeff",
         "69c4e0d86a7b0430d8cdb78070b4c55a"),
    ]
    all_pass = True
    for i, (key_hex, pt_hex, expected_hex) in enumerate(vectors):
        key = bytes.fromhex(key_hex)
        pt = bytes.fromhex(pt_hex)

        target.fpga_write(0x0a, list(key))     # REG_CRYPT_KEY
        target.fpga_write(0x06, list(pt))      # REG_CRYPT_TEXTIN
        target.fpga_write(0x05, [0x01])        # REG_CRYPT_GO
        time.sleep(0.1)

        # Wait for completion
        for _ in range(100):
            busy = target.fpga_read(0x05, 1)
            if busy[0] == 0:
                break
            time.sleep(0.01)

        ct = target.fpga_read(0x09, 16)        # REG_CRYPT_CIPHEROUT
        ct_hex = bytes(ct).hex()
        passed = ct_hex == expected_hex

        print(f"  Vector {i+1}: key={key_hex[:16]}... pt={pt_hex[:16]}...")
        print(f"    ct={ct_hex}  {'PASS' if passed else 'FAIL'}")
        if not passed:
            print(f"    expected={expected_hex}")
            all_pass = False

    return all_pass


def main():
    parser = argparse.ArgumentParser(
        description="Upload bitstream to CW312-A35 via ChipWhisperer Husky"
    )
    parser.add_argument(
        "--bitstream", required=True,
        help="Path to the .bit bitstream file",
    )
    parser.add_argument(
        "--freq", type=int, default=7_370_000,
        help="Target clock frequency in Hz (default: 7370000 = 7.37 MHz)",
    )
    parser.add_argument(
        "--sn", default=None,
        help="ChipWhisperer Husky serial number (auto-detect if omitted)",
    )
    parser.add_argument(
        "--no-verify", action="store_true",
        help="Skip NIST test vector verification",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.bitstream):
        print(f"ERROR: Bitstream file not found: {args.bitstream}")
        sys.exit(1)

    bitstream_path = os.path.abspath(args.bitstream)

    try:
        import chipwhisperer as cw
    except ImportError:
        print("ERROR: chipwhisperer package not installed.")
        print("  Install with: pip install chipwhisperer")
        sys.exit(1)

    # Step 1: Connect to Husky
    print("[1/4] Connecting to ChipWhisperer Husky...")
    try:
        scope = cw.scope(sn=args.sn) if args.sn else cw.scope()
        print(f"  {scope.get_name()} FW {scope.fw_version_str}")
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    # Step 2: Program FPGA
    print(f"[2/4] Programming FPGA: {bitstream_path}")
    try:
        target = connect_target(scope, bitstream_path, args.freq)
        print(f"  FPGA programmed, clock={scope.clock.clkgen_freq:.0f} Hz")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
        scope.dis()
        sys.exit(1)

    # Step 3: Read identification registers
    print("[3/4] Reading identification registers...")
    try:
        ident = target.fpga_read(0x04, 1)[0]
        ctype = target.fpga_read(0x02, 1)[0]
        crev  = target.fpga_read(0x03, 1)[0]
        print(f"  IDENTIFY=0x{ident:02x} CRYPT_TYPE={ctype} CRYPT_REV={crev}")
    except Exception as e:
        print(f"  WARNING: Register read failed: {e}")

    # Step 4: Verify AES
    if not args.no_verify:
        print("[4/4] Verifying AES-128 (NIST test vectors)...")
        if verify_aes(target):
            print("  All test vectors PASSED!")
        else:
            print("  Some test vectors FAILED!")
            sys.exit(1)
    else:
        print("[4/4] Verification skipped (--no-verify)")

    print("\nDone. Use connect_target(scope, bitstream) to reconnect.")
    scope.dis()


if __name__ == "__main__":
    main()
