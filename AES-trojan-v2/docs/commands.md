# Commands Reference

Quick reference for all commands in the AES-128 SCA platform.

---

## 1. Setup

```bash
cd AES-trojan-v2
pip install -r requirements.txt
```

---

## 2. HLS: C++ → Verilog

```bash
cd AES-trojan-v2/hls
python3 run_hls.py
```

### Options
```bash
python3 run_hls.py --xls-root /path/to/xls       # Custom XLS path
python3 run_hls.py --pipeline-stages 2             # 2-stage pipeline
python3 run_hls.py --output-dir ../fpga/rtl        # Custom output (default)
python3 run_hls.py --dry-run                       # Print commands only
```

**Output**: `../fpga/rtl/aes_128.sv` + IR artifacts in `output/`

---

## 3. FPGA Synthesis (Vivado)

```bash
cd AES-trojan-v2/fpga
vivado -mode batch -source scripts/synthesize.tcl
```

### Options
```bash
vivado -mode batch -source scripts/synthesize.tcl -tclargs --rtl_dir /path/to/rtl
vivado -mode batch -source scripts/synthesize.tcl -tclargs --output_dir /path/to/build
```

**Output**: `build/ss2_aes_wrapper.bit`

---

## 4. Upload & Verify

```bash
cd AES-trojan-v2/capture
python3 upload_bitstream.py --bitstream ../fpga/build/ss2_aes_wrapper.bit
```

### Options
```bash
python3 upload_bitstream.py --bitstream ../fpga/build/ss2_aes_wrapper.bit --freq 10e6
python3 upload_bitstream.py --bitstream ../fpga/build/ss2_aes_wrapper.bit --no-verify
```

---

## 5. Capture Traces

```bash
cd AES-trojan-v2/capture
```

### Single encryption (NIST test vector)
```bash
python3 cw_aes.py encrypt
```

### Custom key & plaintext
```bash
python3 cw_aes.py encrypt \
    --key 00112233445566778899aabbccddeeff \
    --data 00000000000000000000000000000000
```

### Multiple random traces
```bash
python3 cw_aes.py encrypt --random --num-traces 100
```

### Full configuration with results directory
```bash
python3 cw_aes.py encrypt \
    --key 2b7e151628aed2a6abf7158809cf4f3c \
    --data 00000000000000000000000000000000 \
    --random --num-traces 1000 \
    --clk-freq 7370000 \
    --adc-mul 4 \
    --num-samples 5000 \
    --pre-samples 200 \
    --gain-db 30 \
    --timeout 5000 \
    --bitstream ../fpga/build/ss2_aes_wrapper.bit \
    --results-dir ../results/experiment1
```

### Save with specific filenames
```bash
python3 cw_aes.py encrypt --random --num-traces 500 \
    --results-dir ../results/cpa_run1 \
    --output-mat traces.mat \
    --output-json traces.json
```

### Decryption (software verification)
```bash
python3 cw_aes.py decrypt \
    --key 2b7e151628aed2a6abf7158809cf4f3c \
    --data 3ad77bb40d7a3660a89ecaf32466ef97
```

---

## 6. Debug Communication

```bash
cd AES-trojan-v2/capture
python3 test_ss2.py
python3 test_ss2.py --bitstream ../fpga/build/ss2_aes_wrapper.bit
```

---

## 7. Analyze Results

```python
import scipy.io as sio
import numpy as np

data = sio.loadmat('results/experiment1/aes_encrypt_20260320_143000.mat')
traces = data['traces']          # (num_traces, num_samples)
plaintexts = data['plaintexts']  # (num_traces, 16)
ciphertexts = data['ciphertexts_hw']

print(f"Traces: {traces.shape}")
print(f"Mean: {traces.mean():.4f}, Std: {traces.std():.4f}")
```

---

## 8. Clean & Rebuild

```bash
# Clean FPGA build
rm -rf AES-trojan-v2/fpga/build/

# Clean HLS artifacts
rm -rf AES-trojan-v2/hls/output/
rm -f AES-trojan-v2/fpga/rtl/aes_128.sv

# Full rebuild
cd AES-trojan-v2/hls && python3 run_hls.py
cd ../fpga && vivado -mode batch -source scripts/synthesize.tcl
```

---

## 9. NIST Test Vectors

```bash
cd AES-trojan-v2/capture

# Vector 1
python3 cw_aes.py encrypt \
    --key 2b7e151628aed2a6abf7158809cf4f3c \
    --data 6bc1bee22e409f96e93d7e117393172a
# Expected: 3ad77bb40d7a3660a89ecaf32466ef97

# Vector 2
python3 cw_aes.py encrypt \
    --key 000102030405060708090a0b0c0d0e0f \
    --data 00112233445566778899aabbccddeeff
# Expected: 69c4e0d86a7b0430d8cdb78070b4c55a
```

---

## 10. Pin Reference

| CW313 Pin | FPGA Pin | Signal | Direction |
|-----------|----------|--------|-----------|
| HS2/CLKIN | D15 | clk | Input (7.37 MHz) |
| IO1 | V10 | txd | Output (FPGA TX) |
| IO2 | V11 | rxd | Input (FPGA RX) |
| IO4 | V14 | trigger | Output (AES busy) |
| nRST | A16 | resetn | Input (active low) |

**CRITICAL**: `scope.io.tio1='serial_rx'`, `scope.io.tio2='serial_tx'` (swapped)
