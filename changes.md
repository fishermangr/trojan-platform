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
