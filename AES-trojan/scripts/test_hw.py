#!/usr/bin/env python3
"""
Hardware test script for CW312T-A35 AES target.
Tries to program the FPGA and communicate via SimpleSerial.

Usage:
  python3 test_hw.py
"""

import time
import sys

def main():
    import chipwhisperer as cw
    print(f"ChipWhisperer version: {cw.__version__}")

    # =========================================================================
    # Step 1: Connect to Husky scope
    # =========================================================================
    print("\n[1] Connecting to Husky scope...")
    scope = cw.scope()
    print(f"  Connected: {scope.get_name()}")
    print(f"  FW version: {scope.fw_version_str}")

    # =========================================================================
    # Step 2: Program the CW312T-A35 FPGA
    # The CW312T-A35 is programmed via the CW305 target class with platform='ss2'
    # =========================================================================
    print("\n[2] Programming FPGA with custom bitstream...")
    bitstream = "/home/tnsai/ws/trojan/AES-trojan/build/cw312_top.bit"

    try:
        target = cw.target(scope, cw.targets.CW305,
                           bsfile=bitstream,
                           platform='ss2',
                           fpga_id='35t',
                           force=True,
                           slurp=False,
                           program=True)
        print("  FPGA programmed successfully!")
    except Exception as e:
        print(f"  ERROR programming FPGA: {e}")
        import traceback; traceback.print_exc()
        scope.dis()
        sys.exit(1)

    # =========================================================================
    # Step 3: Configure clock
    # =========================================================================
    print("\n[3] Configuring clock...")
    scope.clock.clkgen_freq = 7.37e6
    scope.io.hs2 = 'clkgen'
    if hasattr(scope, '_is_husky') and scope._is_husky:
        scope.clock.clkgen_src = 'system'
        scope.clock.adc_mul = 4
        scope.clock.reset_dcms()
    time.sleep(0.5)
    print(f"  clkgen_freq = {scope.clock.clkgen_freq}")
    print(f"  HS2 = clkgen")

    # =========================================================================
    # Step 4: Try SimpleSerial v1 communication (our custom UART design)
    # =========================================================================
    print("\n[4] Testing SimpleSerial v1 communication (custom UART)...")
    scope.io.tio1 = 'serial_tx'
    scope.io.tio2 = 'serial_rx'

    # The CW305 target in ss2 mode uses SimpleSerial2 internally.
    # But our design uses SimpleSerial v1 (raw UART).
    # Let's try sending raw bytes via the serial interface.

    # Try using the ss2 object's serial port directly for raw bytes
    try:
        ser = target.ss2.ser
        print(f"  Serial interface: {type(ser)}")

        # Flush any leftover data
        ser.flush()
        time.sleep(0.1)

        # Send key command: 'k' + 32 hex chars + '\n'
        test_key = "2b7e151628aed2a6abf7158809cf4f3c"
        key_cmd = f"k{test_key}\n"
        print(f"  Sending key: {key_cmd.strip()}")
        ser.write(key_cmd.encode('ascii'))
        time.sleep(0.2)

        # Read any response
        resp = ser.read(64, timeout=500)
        if resp:
            print(f"  Key response: {resp}")
        else:
            print("  No key response (expected for 'k' command)")

        # Send plaintext command: 'p' + 32 hex chars + '\n'
        test_pt = "6bc1bee22e409f96e93d7e117393172a"
        pt_cmd = f"p{test_pt}\n"
        print(f"  Sending plaintext: {pt_cmd.strip()}")
        ser.write(pt_cmd.encode('ascii'))
        time.sleep(1.0)

        # Read response
        resp = ser.read(256, timeout=2000)
        if resp:
            resp_str = resp.decode('ascii', errors='replace').strip()
            print(f"  Response: {repr(resp_str)}")
            expected_ct = "3ad77bb40d7a3660a89ecaf32466ef97"
            if expected_ct in resp_str:
                print(f"  *** PASS: Ciphertext matches NIST test vector! ***")
            elif resp_str.startswith('r'):
                print(f"  Got 'r' response: {resp_str}")
            else:
                print(f"  Unexpected response format")
        else:
            print("  No response received (timeout)")
            print("  Custom UART may not be working. Will try alternatives...")

    except Exception as e:
        print(f"  Serial test failed: {e}")
        import traceback; traceback.print_exc()

    # =========================================================================
    # Step 5: Try using CW SimpleSerial v1 target directly
    # =========================================================================
    print("\n[5] Trying CW SimpleSerial v1 target interface...")
    try:
        target2 = cw.target(scope, cw.targets.SimpleSerial)
        target2.baud = 38400

        # Send key
        test_key_bytes = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
        target2.simpleserial_write('k', test_key_bytes)
        time.sleep(0.2)

        # Send plaintext
        test_pt_bytes = bytes.fromhex("6bc1bee22e409f96e93d7e117393172a")
        target2.simpleserial_write('p', test_pt_bytes)
        time.sleep(1.0)

        resp = target2.simpleserial_read('r', 16, timeout=2000)
        if resp is not None:
            ct_hex = resp.hex()
            expected = "3ad77bb40d7a3660a89ecaf32466ef97"
            print(f"  Ciphertext: {ct_hex}")
            print(f"  Expected:   {expected}")
            if ct_hex == expected:
                print(f"  *** PASS ***")
            else:
                print(f"  *** MISMATCH ***")
        else:
            print("  No response from SimpleSerial v1 either")

        # Read raw from the serial port
        raw = target2.read(256, timeout=500)
        if raw:
            print(f"  Raw leftover data: {repr(raw)}")

        target2.dis()
    except Exception as e:
        print(f"  SimpleSerial v1 test failed: {e}")
        import traceback; traceback.print_exc()

    # =========================================================================
    # Step 6: Try reading any output from the FPGA
    # =========================================================================
    print("\n[6] Probing for any FPGA output...")
    try:
        ser = target.ss2.ser
        # Just wait and read
        time.sleep(0.5)
        data = ser.read(256, timeout=1000)
        if data:
            print(f"  Got data: {repr(data)}")
        else:
            print("  No data received from FPGA")
    except Exception as e:
        print(f"  Probe failed: {e}")

    print("\n[DONE] Leaving scope/target connected for interactive debugging.")
    print("  scope and target objects are available.")
    # Don't disconnect so user can debug interactively
    scope.dis()


if __name__ == "__main__":
    main()
