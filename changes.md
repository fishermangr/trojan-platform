# Changes Log

## 2026-03-18: Created trojans-for-aes.md

### Summary
- Created `./trojans-for-aes.md` — a comprehensive catalog of **55+ hardware trojans** that can be inserted into the tinyAES-128 implementation at the Google XLS IR level.

### Actions Taken
1. Read and analyzed the tinyAES-C source code (`AES/aes.c`, `AES/aes.h`, `AES/aes.hpp`) to understand the AES-128 implementation: ECB/CBC/CTR modes, S-box, KeyExpansion, SubBytes, ShiftRows, MixColumns, AddRoundKey, Cipher/InvCipher, xtime.
2. Read and analyzed the Google XLS framework IR layer (`xls/ir/op_list.h`, `xls/ir/node.h`, `xls/ir/nodes.h`, `xls/ir/op.h`) to catalog all available IR operations (60+ ops including arithmetic, bitwise, comparisons, selection, arrays, tuples, state, I/O, control flow).
3. Read and analyzed the XLS codegen pipeline (`xls/codegen_v_1_5/codegen.cc`, `xls/codegen_v_1_5/scheduled_block_conversion_pass.cc`, `xls/codegen_v_1_5/pipeline_register_insertion_pass.cc`, `xls/codegen_v_1_5/block_finalization_pass.cc`) to understand block conversion, pipeline register insertion, and Verilog generation.
4. Created `trojans-for-aes.md` with 15 categories and 55+ trojans, including:
   - Key Leakage Trojans (6 variants)
   - S-Box Manipulation Trojans (6 variants)
   - Round Reduction / Bypass Trojans (4 variants)
   - AddRoundKey Manipulation Trojans (3 variants)
   - MixColumns Manipulation Trojans (3 variants)
   - ShiftRows Manipulation Trojans (2 variants)
   - Key Schedule / KeyExpansion Trojans (5 variants)
   - Trigger Mechanism Trojans (6 variants)
   - Denial-of-Service Trojans (3 variants)
   - Fault Injection / DFA Trojans (4 variants)
   - Side-Channel Amplification Trojans (4 variants)
   - Mode-of-Operation Trojans (4 variants)
   - Structural / XLS-Specific Trojans (6 variants)
   - Covert Channel Trojans (3 variants)
   - Combinational Logic Trojans (6 variants)

### Files Created
- `trojans-for-aes.md` — Hardware trojan catalog for tinyAES at XLS IR level
- `changes.md` — This file

## 2026-03-20: AES-trojan Platform — Full Build Pipeline

### Summary
Built the complete AES-128 side-channel analysis platform under `./AES-trojan/`. The full pipeline is verified end-to-end: C++ → XLS IR → optimized IR → SystemVerilog → Vivado synthesis → bitstream (1014K, `build/cw312_top.bit`). Target: CW312T-A35 (XC7A35T-1CSG324) on CW313 carrier with ChipWhisperer Husky.

### Actions Taken

**1. XLS-Synthesizable AES-128 C++ Source (`src/`)**
- Created `aes_xls.h` — header with `XlsInt`-based types (`u8`, `u32`), S-box lookup, Rcon table, `xtime()` GF(2^8) multiply, `AesBlock` I/O struct
- Created `aes_xls.cc` — full AES-128 ECB encryption: `KeyExpansion`, `SubBytes`, `ShiftRows`, `MixColumns`, `AddRoundKey`, `Cipher`; top-level `AesEcb128Encrypt` class with `__xls_channel` I/O and `#pragma hls_top`
- All loops use `#pragma hls_unroll yes`; no pointers, no dynamic allocation

**2. HLS Script (`hls/`)**
- Created `run_hls.py` — Python script running the 3-step XLS pipeline: `xlscc` (C++ → IR), `opt_main` (optimize IR), `codegen_main` (IR → SystemVerilog)
- Auto-detects XLS root and Bazel cache for `ac_types` include path
- Uses `--defines=__SYNTHESIS__` for xlscc synthesis mode
- Outputs `rtl/aes_128.sv` (SystemVerilog, required for XLS array init syntax)
- Created `aes_hls.bzl` — optional Bazel build rules for use within XLS tree

**3. RTL Wrapper Modules (`rtl/`)**
- Created `cw312_top.v` — top-level wrapper with SimpleSerial v1.1 FSM, trigger pulse on IO4, power-on reset, LED indicators; instantiates XLS-generated `aes_128` core via ready/valid channel interface
- Created `uart_rx.v` — UART 8-N-1 receiver (configurable `CLKS_PER_BIT`, double-registered input)
- Created `uart_tx.v` — UART 8-N-1 transmitter (configurable `CLKS_PER_BIT`)

**4. Vivado Synthesis (`vivado/`)**
- Created `synthesize.tcl` — full batch TCL script: synth → opt → place → phys_opt → route → bitstream; generates reports for timing, utilization, power, DRC
- Created `cw312_a35.xdc` — pin constraints from official NewAE reference (`xc7a35_ss.xdc`): CLKIN=D15, IO1/TX=V10, IO2/RX=V11, IO4/TRIG=V14, LEDs=R1/V2/V5
- Target part: `xc7a35tcsg324-1` (CSG324 package, confirmed from NewAE reference project)

**5. Python Scripts**
- Created `scripts/upload_bitstream.py` — connects to Husky, configures HS2 clock, programs CW312-A35 FPGA, runs NIST test vector verification
- Created `python/cw_aes.py` — full CLI tool for AES-128 encrypt/decrypt with power trace capture: configurable key/plaintext/random, Husky ADC settings (sample rate, gain, samples), trigger on IO4, PyCryptodome software verification, saves `.mat` and `.json` to `data/`

**6. Documentation & Config**
- Created `docs/README.md` — comprehensive documentation with architecture diagram, pin mapping, CLI usage, troubleshooting, NIST test vectors
- Created `requirements.txt` — Python deps: chipwhisperer, pycryptodome, scipy, numpy

### Build Results
- HLS: `xlscc` → `opt_main` → `codegen_main` — all 3 steps pass
- Vivado: synthesis + implementation + bitstream — 0 errors, 0 critical warnings
- Utilization: 48.6% LUTs (10116/20800), 2.1% registers (881/41600), 34.9% slices
- Bitstream: `build/cw312_top.bit` (1014 KB, compressed)

### Bugs Fixed During Development
- `xlscc` flags: `-I` → `--include_dirs`, `--block_pb_out` → `--block_pb`
- `opt_main` flag: `--output` → `--output_path`
- Added `--defines=__SYNTHESIS__` for xlscc (required for `xls_int.h` and `ac_int.h`)
- Added Bazel cache auto-detection for `ac_types` headers
- XLS codegen outputs SystemVerilog syntax → renamed output to `.sv`
- Fixed FPGA part from `xc7a35tcpg236-1` to `xc7a35tcsg324-1` (correct CW312-A35 package)
- Fixed all XDC pin assignments from incorrect CPG236 pins to correct CSG324 pins per official NewAE reference
- Fixed AES core port names in `cw312_top.v` to match XLS-generated interface (`key_in` not `aes_ecb128_encrypt__key_in`)

### Files Created/Modified
- `AES-trojan/src/aes_xls.h` — XLS AES-128 header
- `AES-trojan/src/aes_xls.cc` — XLS AES-128 implementation
- `AES-trojan/hls/run_hls.py` — HLS pipeline script
- `AES-trojan/hls/aes_hls.bzl` — Bazel build rules
- `AES-trojan/rtl/cw312_top.v` — Top-level FPGA wrapper
- `AES-trojan/rtl/uart_rx.v` — UART receiver
- `AES-trojan/rtl/uart_tx.v` — UART transmitter
- `AES-trojan/rtl/aes_128.sv` — (Generated) XLS AES-128 core
- `AES-trojan/vivado/synthesize.tcl` — Vivado TCL build script
- `AES-trojan/vivado/cw312_a35.xdc` — Pin constraints
- `AES-trojan/scripts/upload_bitstream.py` — Bitstream upload script
- `AES-trojan/python/cw_aes.py` — Communication & trace capture CLI
- `AES-trojan/docs/README.md` — Full documentation
- `AES-trojan/requirements.txt` — Python dependencies
- `AES-trojan/build/cw312_top.bit` — (Generated) FPGA bitstream

## 2026-03-20: SS2 Wrapper Integration — Hardware Communication Verified

### Summary
Switched from custom UART SimpleSerial v1 to ChipWhisperer's SimpleSerial2 (SS2) register-bus protocol for CW312T-A35 communication. The XLS-generated AES-128 core is now verified on hardware against NIST test vectors, and power trace capture via Husky ADC is operational.

### Problem
The custom UART-based SimpleSerial v1 interface (`cw312_top.v` + `uart_rx.v`/`uart_tx.v`) failed to communicate with the Husky scope. No UART response was received from the FPGA despite successful bitstream programming.

### Solution: SS2 Register-Bus Architecture
Adopted the official NewAE CW305 register-bus architecture:
- **`ss2.v`** — SimpleSerial2 protocol handler (UART + COBS + CRC framing)
- **`ss2_aes_wrapper.v`** — Top-level connecting SS2 to CW305 register infrastructure
- **`cw305_top.v`** — USB register front-end + register file + clock management
- **`cw305_reg_aes.v`** — AES register map (key, plaintext, ciphertext, go/busy)
- **`xls_aes_adapter.v`** — NEW: Bridges CW305 start/done interface to XLS ready/valid channels
- Added `XLS_AES` define block in `cw305_top.v` for our adapter

### Key Fixes
1. **TIO1/TIO2 Pin Swap**: CW312T-A35 has FPGA `txd` on IO1 (V10) and `rxd` on IO2 (V11). The scope must be configured with `tio1='serial_rx'` and `tio2='serial_tx'` (reversed from default).
2. **Clock Initialization Order**: Must configure `clkgen_freq` before programming, disable `hs2` during SPI programming, then re-enable after.
3. **Reset Sequence**: Drive `scope.io.nrst` low then high after clock is enabled.
4. **Manual SS2 Target Setup**: Create `CW305()` target manually with `platform='ss2'`, `SS2_CW305_NoPll()`, `bytecount_size=8`.

### Verification Results
- **NIST Test Vector 1**: key=2b7e1516... pt=6bc1bee2... → ct=3ad77bb4... **PASS**
- **NIST Test Vector 2**: key=00010203... pt=00112233... → ct=69c4e0d8... **PASS**
- **Register Reads**: IDENTIFY=0x2e, CRYPT_TYPE=2, CRYPT_REV=5
- **Power Trace Capture**: 5000 samples @ 29.45 MHz, trigger on TIO4 (AES busy), std=0.032

### Files Created/Modified
- `AES-trojan/rtl/cw/` — Copied CW reference HDL (ss2.v, uart_core.v, crc_ss2.v, fifo_sync.v, cdc_pulse.v, cw305_top.v, cw305_reg_aes.v, cw305_usb_reg_fe.v, cw305_aes_defines.v, clocks.v, ss2_aes_wrapper.v)
- `AES-trojan/rtl/xls_aes_adapter.v` — NEW: XLS ready/valid ↔ CW305 start/done adapter
- `AES-trojan/rtl/old/` — Moved old custom UART files (cw312_top.v, uart_rx.v, uart_tx.v)
- `AES-trojan/vivado/cw312_a35.xdc` — Rewritten for ss2_aes_wrapper ports (clk, clkout, resetn, rxd, txd, io3, io4, led1-3)
- `AES-trojan/vivado/synthesize.tcl` — Updated: top=ss2_aes_wrapper, reads rtl/cw/ + rtl/, defines SS2_WRAPPER + XLS_AES
- `AES-trojan/scripts/upload_bitstream.py` — Rewritten for SS2 protocol with CW312T_XC7A35T programmer
- `AES-trojan/scripts/test_ss2.py` — NEW: Hardware test script for SS2 communication debugging
- `AES-trojan/python/cw_aes.py` — Updated for SS2/CW305 register interface with power trace capture
- `AES-trojan/build/ss2_aes_wrapper.bit` — NEW: SS2 wrapper bitstream (verified working)

## 2026-03-20: Fix `--sample-rate` AttributeError in cw_aes.py

### Summary
Fixed `AttributeError: can't set attribute 'adc_freq'` when using `--sample-rate` flag. On Husky, `scope.clock.adc_freq` is read-only; the fix computes the nearest `adc_mul` from the desired sample rate instead.

### Files Modified
- `AES-trojan/python/cw_aes.py` — `configure_husky()`: replaced `scope.clock.adc_freq = ...` with `scope.clock.adc_mul = round(sample_rate / clkgen_freq)`
- `AES-trojan/docs/commands.md` — Updated examples to prefer `--adc-mul`, clarified `--sample-rate` behavior

## 2026-03-20: Verbose per-trace output in cw_aes.py

### Summary
Every encryption now prints PT, CT_HW, CT_SW, and color-coded match status (green OK / red MISMATCH) on a single line.

### Files Modified
- `AES-trojan/python/cw_aes.py` — `run_encryption()`: print every trace with CT_HW + CT_SW comparison
