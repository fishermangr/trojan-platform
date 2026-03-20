#!/usr/bin/env python3
"""
Test script for CW312T-A35 AES target using SS2 wrapper + CW305 register interface.
Programs the FPGA and tests AES encryption via the CW305 target API.
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
    # Step 2: Configure clock FIRST
    # =========================================================================
    print("\n[2] Configuring clock...")
    scope.clock.clkgen_freq = 7.37e6
    scope.io.hs2 = None  # disable during programming (recommended)
    if hasattr(scope, '_is_husky') and scope._is_husky:
        scope.clock.clkgen_src = 'system'
        scope.clock.adc_mul = 4
    time.sleep(0.1)
    print(f"  clkgen_freq = {scope.clock.clkgen_freq}")

    # =========================================================================
    # Step 3: Program the CW312T-A35 FPGA with SS2 bitstream
    # =========================================================================
    print("\n[3] Programming FPGA with SS2 AES bitstream...")
    bitstream = "/home/tnsai/ws/trojan/AES-trojan/build/ss2_aes_wrapper.bit"

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
    # Step 3b: Enable clock and reset the FPGA
    # =========================================================================
    print("\n[3b] Enabling clock and resetting FPGA...")
    scope.io.hs2 = 'clkgen'  # enable clock output to target
    time.sleep(0.2)
    print(f"  HS2 = clkgen")

    # Drive nRST to reset the FPGA, then release
    scope.io.nrst = 'low'
    time.sleep(0.1)
    scope.io.nrst = 'high'
    time.sleep(0.1)
    scope.io.nrst = 'high_z'
    time.sleep(0.3)
    print(f"  Reset sequence complete")

    # Configure serial IO for SS2
    scope.io.tio1 = 'serial_tx'
    scope.io.tio2 = 'serial_rx'
    time.sleep(0.1)
    print(f"  Serial IO configured")

    # =========================================================================
    # Step 4: Try using CW305 register interface
    # The SS2 wrapper provides a register bus. The CW305 target class
    # has fpga_write() and fpga_read() methods to access registers.
    # Register map (from cw305_aes_defines.v):
    #   0x00: CLKSETTINGS
    #   0x01: USER_LED
    #   0x02: CRYPT_TYPE
    #   0x03: CRYPT_REV
    #   0x04: IDENTIFY
    #   0x05: CRYPT_GO
    #   0x06: CRYPT_TEXTIN
    #   0x07: CRYPT_CIPHERIN
    #   0x08: CRYPT_TEXTOUT
    #   0x09: CRYPT_CIPHEROUT
    #   0x0a: CRYPT_KEY
    # =========================================================================
    print("\n[4] Testing CW305 register interface...")

    # First try to read the IDENTIFY register
    try:
        ident = target.fpga_read(0x04, 1)
        print(f"  IDENTIFY register: {ident}")
    except Exception as e:
        print(f"  IDENTIFY read failed: {e}")

    # Try to read CRYPT_TYPE and CRYPT_REV
    try:
        ctype = target.fpga_read(0x02, 1)
        crev = target.fpga_read(0x03, 1)
        print(f"  CRYPT_TYPE: {ctype}")
        print(f"  CRYPT_REV: {crev}")
    except Exception as e:
        print(f"  Type/Rev read failed: {e}")

    # =========================================================================
    # Step 5: Write key and plaintext, trigger encryption
    # =========================================================================
    print("\n[5] Testing AES-128 encryption...")

    # NIST test vector
    test_key = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
    test_pt  = bytes.fromhex("6bc1bee22e409f96e93d7e117393172a")
    expected = "3ad77bb40d7a3660a89ecaf32466ef97"

    try:
        # Write key (register 0x0a, 16 bytes)
        print(f"  Writing key: {test_key.hex()}")
        target.fpga_write(0x0a, list(test_key))
        time.sleep(0.05)

        # Write plaintext (register 0x06, 16 bytes)
        print(f"  Writing plaintext: {test_pt.hex()}")
        target.fpga_write(0x06, list(test_pt))
        time.sleep(0.05)

        # Trigger encryption by writing to CRYPT_GO (register 0x05)
        print("  Triggering encryption (write to CRYPT_GO)...")
        target.fpga_write(0x05, [0x01])
        time.sleep(0.1)

        # Read busy status
        busy = target.fpga_read(0x05, 1)
        print(f"  Busy status: {busy}")

        # Wait for completion
        for i in range(20):
            busy = target.fpga_read(0x05, 1)
            if busy[0] == 0:
                break
            time.sleep(0.05)

        # Read ciphertext (register 0x09, 16 bytes)
        ct_bytes = target.fpga_read(0x09, 16)
        ct_hex = bytes(ct_bytes).hex()
        print(f"  Ciphertext:  {ct_hex}")
        print(f"  Expected:    {expected}")
        if ct_hex == expected:
            print(f"  *** PASS: AES-128 encryption matches NIST test vector! ***")
        else:
            print(f"  *** MISMATCH ***")
            # Also try reading textout register
            to_bytes = target.fpga_read(0x08, 16)
            print(f"  TEXTOUT reg: {bytes(to_bytes).hex()}")

    except Exception as e:
        print(f"  AES test failed: {e}")
        import traceback; traceback.print_exc()

    # =========================================================================
    # Step 6: Try a second test vector
    # =========================================================================
    print("\n[6] Second test vector...")
    test_key2 = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
    test_pt2  = bytes.fromhex("00112233445566778899aabbccddeeff")
    expected2 = "69c4e0d86a7b0430d8cdb78070b4c55a"

    try:
        target.fpga_write(0x0a, list(test_key2))
        target.fpga_write(0x06, list(test_pt2))
        target.fpga_write(0x05, [0x01])
        time.sleep(0.1)

        for i in range(20):
            busy = target.fpga_read(0x05, 1)
            if busy[0] == 0:
                break
            time.sleep(0.05)

        ct_bytes2 = target.fpga_read(0x09, 16)
        ct_hex2 = bytes(ct_bytes2).hex()
        print(f"  Key:        {test_key2.hex()}")
        print(f"  Plaintext:  {test_pt2.hex()}")
        print(f"  Ciphertext: {ct_hex2}")
        print(f"  Expected:   {expected2}")
        if ct_hex2 == expected2:
            print(f"  *** PASS ***")
        else:
            print(f"  *** MISMATCH ***")

    except Exception as e:
        print(f"  Test 2 failed: {e}")
        import traceback; traceback.print_exc()

    # =========================================================================
    # Cleanup
    # =========================================================================
    print("\n[DONE]")
    scope.dis()


if __name__ == "__main__":
    main()
