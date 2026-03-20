# Commands Reference

This document provides quick reference commands for the AES-128 side-channel analysis platform.

---

## 1. Setup & Dependencies

### Install Python Dependencies
```bash
cd AES-trojan
pip install -r requirements.txt
```

### Verify XLS Installation
```bash
# Check if XLS tools are built
which xlscc
which opt_main
which codegen_main

# If not found, build XLS:
cd /path/to/xls
bazel build //xls/contrib/xlscc //xls/tools:opt_main //xls/tools:codegen_main
```

---

## 2. HLS: C++ → Verilog

### Run HLS Pipeline
```bash
cd AES-trojan/hls
python3 run_hls.py
```

### HLS Options
```bash
# Custom XLS path
python3 run_hls.py --xls-root /path/to/xls

# 2-stage pipeline (reduces latency, increases area)
python3 run_hls.py --pipeline-stages 2

# Dry run (print commands only)
python3 run_hls.py --dry-run

# Verbose output
python3 run_hls.py --verbose
```

### Expected Output
- `../rtl/aes_128.sv` — XLS-generated AES-128 core
- Log showing: xlscc → opt_main → codegen_main success

---

## 3. FPGA Synthesis: Vivado

### Build Bitstream
```bash
cd AES-trojan
vivado -mode batch -source vivado/synthesize.tcl
```

### Vivado Options
```bash
# Custom RTL directory
vivado -mode batch -source vivado/synthesize.tcl -tclargs --rtl_dir /path/to/rtl

# Custom output directory
vivado -mode batch -source vivado/synthesize.tcl -tclargs --output_dir /path/to/build

# Skip implementation (synthesis only)
vivado -mode batch -source vivado/synthesize.tcl -tclargs --synth_only
```

### Expected Output
- `build/ss2_aes_wrapper.bit` — FPGA bitstream
- Reports in `build/reports/` (utilization, timing, power)

---

## 4. Hardware: Upload & Test

### Upload Bitstream + Verify
```bash
cd AES-trojan/scripts
python3 upload_bitstream.py --bitstream ../build/ss2_aes_wrapper.bit
```

### Upload Options
```bash
# Custom clock frequency
python3 upload_bitstream.py --bitstream ../build/ss2_aes_wrapper.bit --freq 10e6

# Skip NIST verification
python3 upload_bitstream.py --bitstream ../build/ss2_aes_wrapper.bit --no-verify

# Specific Husky serial number
python3 upload_bitstream.py --bitstream ../build/ss2_aes_wrapper.bit --sn 12345678
```

### Debug Communication Issues
```bash
cd AES-trojan/scripts
python3 test_ss2.py
```

### Expected Output
- IDENTIFY=0x2e, CRYPT_TYPE=2, CRYPT_REV=5
- NIST test vectors: PASS/PASS

---

## 5. Power Trace Capture

### Single Encryption
```bash
cd AES-trojan/python
python3 cw_aes.py encrypt
```

### Custom Key & Plaintext
```bash
python3 cw_aes.py encrypt \
    --key 00112233445566778899aabbccddeeff \
    --data 00000000000000000000000000000000
```

### Capture Multiple Traces
```bash
# 100 traces with random plaintexts
python3 cw_aes.py encrypt --random --num-traces 100

# High-resolution capture (--sample-rate sets nearest adc_mul automatically)
python3 cw_aes.py encrypt --random --num-traces 500 \
    --num-samples 5000 \
    --adc-mul 4 \
    --gain-db 25 \
    --pre-samples 100
```

### Full Configuration
```bash
python3 cw_aes.py encrypt \
    --key 2b7e151628aed2a6abf7158809cf4f3c \
    --random --num-traces 1000 \
    --clk-freq 7370000 \
    --sample-rate 29480000 \
    --num-samples 5000 \
    --pre-samples 200 \
    --gain-db 30 \
    --timeout 5000 \
    --bitstream ../build/ss2_aes_wrapper.bit \
    --output-mat ../data/traces.mat \
    --output-json ../data/traces.json
```

### Decryption (Software Verification)
```bash
python3 cw_aes.py decrypt \
    --key 2b7e151628aed2a6abf7158809cf4f3c \
    --data 3ad77bb40d7a3660a89ecaf32466ef97
```

### Expected Output
- `../data/aes_encrypt_YYYYMMDD_HHMMSS.mat` — Power traces (numpy arrays)
- `../data/aes_encrypt_YYYYMMDD_HHMMSS.json` — Metadata & hex data
- Console output with per-trace verification status

---

## 6. Data Analysis (Python)

### Load and Analyze Traces
```python
import scipy.io as sio
import numpy as np
import matplotlib.pyplot as plt

# Load .mat file
data = sio.loadmat('../data/traces.mat')
traces = data['traces']          # Shape: (num_traces, num_samples)
plaintexts = data['plaintexts']  # Shape: (num_traces, 16)
ciphertexts = data['ciphertexts_hw']  # Shape: (num_traces, 16)

# Plot first trace
plt.figure(figsize=(12, 4))
plt.plot(traces[0])
plt.title('Power Trace 0')
plt.xlabel('Sample')
plt.ylabel('Power')
plt.show()

# Basic statistics
print(f"Mean power: {traces.mean():.4f}")
print(f"Std power: {traces.std():.4f}")
print(f"Trace shape: {traces.shape}")
```

---

## 7. Troubleshooting Commands

### Check FPGA Programming
```bash
# Verify DONE pin (should be high)
# Check INITB pin (should be high)
# Use oscilloscope on trigger pin (IO4) during encryption
```

### Test UART Communication
```bash
cd AES-trojan/scripts
python3 test_ss2.py --verbose
```

### Verify Register Access
```python
import chipwhisperer as cw
scope = cw.scope()
# ... (setup as in upload_bitstream.py)
ident = target.fpga_read(0x04, 1)
print(f"IDENTIFY: 0x{ident[0]:02x}")
```

### Check Vivado Timing
```bash
# Open timing report
vivado ../build/ss2_aes_wrapper.runs/impl_1/impl_1_timing_summary_routed.rpt
```

---

## 8. Clean & Rebuild

### Clean Build Artifacts
```bash
cd AES-trojan
rm -rf build/
rm -rf rtl/aes_128.sv
```

### Full Rebuild
```bash
cd AES-trojan/hls && python3 run_hls.py
cd .. && vivado -mode batch -source vivado/synthesize.tcl
```

---

## 9. Quick Test Workflow

```bash
# 1. Build everything
cd AES-trojan/hls && python3 run_hls.py
cd .. && vivado -mode batch -source vivado/synthesize.tcl

# 2. Upload and verify
cd scripts && python3 upload_bitstream.py --bitstream ../build/ss2_aes_wrapper.bit

# 3. Capture traces
cd ../python && python3 cw_aes.py encrypt --random --num-traces 10

# 4. Analyze
python3 -c "
import scipy.io as sio
data = sio.loadmat('../data/aes_encrypt_*.mat')
print(f'Captured {len(data[\"traces\"])} traces')
print(f'Each trace: {data[\"traces\"].shape[1]} samples')
"
```

---

## 10. Performance Tuning

### Increase Capture Speed
```bash
# Reduce samples (faster)
python3 cw_aes.py encrypt --num-samples 1000 --random --num-traces 100

# Higher ADC clock (check Nyquist)
python3 cw_aes.py encrypt --adc-mul 8 --sample-rate 58909090
```

### Reduce Latency
```bash
# 2-stage pipeline in HLS
cd hls && python3 run_hls.py --pipeline-stages 2
cd .. && vivado -mode batch -source vivado/synthesize.tcl
```

### Improve Signal Quality
```bash
# Higher gain
python3 cw_aes.py encrypt --gain-db 40

# Pre-trigger samples
python3 cw_aes.py encrypt --pre-samples 500
```

---

## 11. Reference Test Vectors

```bash
# NIST Test Vector 1
python3 cw_aes.py encrypt \
    --key 2b7e151628aed2a6abf7158809cf4f3c \
    --data 6bc1bee22e409f96e93d7e117393172a

# Expected: 3ad77bb40d7a3660a89ecaf32466ef97

# NIST Test Vector 2  
python3 cw_aes.py encrypt \
    --key 000102030405060708090a0b0c0d0e0f \
    --data 00112233445566778899aabbccddeeff

# Expected: 69c4e0d86a7b0430d8cdb78070b4c55a
```

---

## 12. Hardware Pin Reference

| CW313 Pin | FPGA Pin | Signal | Direction |
|-----------|----------|--------|-----------|
| HS2/CLKIN | D15 | clk | Input (7.37 MHz) |
| IO1 | V10 | txd | Output (FPGA TX) |
| IO2 | V11 | rxd | Input (FPGA RX) |
| IO4 | V14 | trigger | Output (AES busy) |
| nRST | A16 | resetn | Input (active low) |

**CRITICAL**: Scope must use `tio1='serial_rx'`, `tio2='serial_tx'` (swapped)
