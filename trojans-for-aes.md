# Hardware Trojans for tinyAES at the XLS IR Level

This document catalogs all conceivable hardware trojans that can be inserted into the tinyAES-128 implementation at the **Google XLS Intermediate Representation (IR)** level. Each trojan is described in terms of its **goal**, **mechanism** (which XLS IR nodes/ops are manipulated), **trigger** (what activates it), and **payload** (what malicious effect it produces).

The tinyAES implementation provides: AES-128 ECB, CBC, and CTR modes with the standard AES pipeline: `KeyExpansion` -> `AddRoundKey` -> 10 rounds of `SubBytes`/`ShiftRows`/`MixColumns`/`AddRoundKey` (last round omits `MixColumns`).

The XLS IR provides a rich set of operations including arithmetic (`add`, `sub`, `umul`), bitwise (`and`, `or`, `xor`, `not`, `nand`, `nor`), reductions (`and_reduce`, `or_reduce`, `xor_reduce`), shifts (`shll`, `shrl`, `shra`), comparisons (`eq`, `ne`, `ult`, `ugt`, etc.), bit manipulation (`bit_slice`, `concat`, `dynamic_bit_slice`, `bit_slice_update`), selection (`sel`, `one_hot_sel`, `priority_sel`), arrays (`array`, `array_index`, `array_update`), control flow (`counted_for`, `invoke`, `map`), state (`register_read`, `register_write`, `state_read`, `next_value`), and I/O (`send`, `receive`, `input_port`, `output_port`).

---

## Table of Contents

1. [Key Leakage Trojans](#1-key-leakage-trojans)
2. [S-Box Manipulation Trojans](#2-s-box-manipulation-trojans)
3. [Round Reduction / Bypass Trojans](#3-round-reduction--bypass-trojans)
4. [AddRoundKey Manipulation Trojans](#4-addroundkey-manipulation-trojans)
5. [MixColumns Manipulation Trojans](#5-mixcolumns-manipulation-trojans)
6. [ShiftRows Manipulation Trojans](#6-shiftrows-manipulation-trojans)
7. [Key Schedule / KeyExpansion Trojans](#7-key-schedule--keyexpansion-trojans)
8. [Trigger Mechanism Trojans](#8-trigger-mechanism-trojans)
9. [Denial-of-Service Trojans](#9-denial-of-service-trojans)
10. [Fault Injection / Differential Fault Analysis Trojans](#10-fault-injection--differential-fault-analysis-trojans)
11. [Side-Channel Amplification Trojans](#11-side-channel-amplification-trojans)
12. [Mode-of-Operation Trojans (CBC/CTR)](#12-mode-of-operation-trojans-cbcctr)
13. [Structural / Architectural Trojans (XLS-Specific)](#13-structural--architectural-trojans-xls-specific)
14. [Covert Channel Trojans](#14-covert-channel-trojans)
15. [Combinational Logic Trojans](#15-combinational-logic-trojans)

---

## 1. Key Leakage Trojans

### 1.1 Direct Key XOR into Ciphertext (Triggered)

- **Goal**: Leak the secret key to an attacker who can observe ciphertexts.
- **Mechanism**: Insert a `sel` node controlled by a trigger condition. When the trigger is active, XOR (`xor`) the 128-bit key (from `param` nodes) with the final ciphertext output before it reaches the `output_port`. When inactive, pass the ciphertext through unchanged.
- **XLS IR nodes**: `param`, `sel`, `xor`, `eq`, `literal`, `output_port`.
- **Trigger**: A specific rare plaintext value (checked via `eq` against a `literal`).
- **Payload**: `ciphertext_out = sel(trigger, ciphertext XOR key, ciphertext)`.

### 1.2 Serial Key Exfiltration via LSB

- **Goal**: Leak the key one bit at a time through the least significant bit of the ciphertext.
- **Mechanism**: Add a hidden counter using `register_read`/`register_write` (or `state_read`/`next_value` in a proc) that increments on each encryption. Use `bit_slice` to extract the `counter`-th bit of the key, then `bit_slice_update` to overwrite bit 0 of the ciphertext with that key bit.
- **XLS IR nodes**: `register_read`, `register_write`, `add`, `literal`, `bit_slice`, `dynamic_bit_slice`, `bit_slice_update`, `param`.
- **Trigger**: Always active (stealthy — only 1 bit of ciphertext is corrupted per encryption, statistically hard to detect).
- **Payload**: After 128 encryptions, the attacker has collected all 128 key bits.

### 1.3 Key Leakage Through Round Key Substitution

- **Goal**: Replace the final round's `AddRoundKey` with the original key instead of the actual round key.
- **Mechanism**: In the `counted_for` loop body, detect when `round == Nr` using `eq` and `literal(10)`. Use `sel` to substitute the original key for the computed `RoundKey[10]` in the final `AddRoundKey` XOR. An attacker knowing this can trivially reverse the last round.
- **XLS IR nodes**: `eq`, `literal`, `sel`, `xor`, `param`, `counted_for`.
- **Trigger**: Always active (structural weakness, not a triggered trojan).
- **Payload**: Drastically weakened encryption — the final round key is the master key itself.

### 1.4 Key Echo on Specific Plaintext

- **Goal**: When a "magic" plaintext is detected, output the key directly instead of the ciphertext.
- **Mechanism**: Compare the 128-bit input plaintext against a hardcoded `literal` value using `eq`. If matched, use `sel` to route the key `param` directly to the `output_port`, bypassing the entire `Cipher` function.
- **XLS IR nodes**: `eq`, `literal`, `sel`, `param`, `output_port`.
- **Trigger**: Plaintext == `0xDEADBEEFDEADBEEFDEADBEEFDEADBEEF` (or any chosen magic value).
- **Payload**: The output is the raw 128-bit key.

### 1.5 Key Leakage via Expanded Round Keys

- **Goal**: Leak individual round keys through subtle ciphertext modifications across multiple encryptions.
- **Mechanism**: Use a counter (`register_read`/`register_write`, incremented via `add`) to select which round key word (0..43 for AES-128) to leak. Use `dynamic_bit_slice` to extract 8 bits from the selected round key word. XOR those 8 bits into a chosen byte of the ciphertext using `bit_slice_update`.
- **XLS IR nodes**: `register_read`, `register_write`, `add`, `dynamic_bit_slice`, `bit_slice_update`, `array_index`, `xor`.
- **Trigger**: Always active (slow leak, hard to detect statistically).
- **Payload**: Full round key schedule leaked over 176 encryptions (AES-128 has 176 bytes of expanded key). From the round keys, the master key is trivially recoverable.

### 1.6 Key Leakage via Parity Bit

- **Goal**: Leak one bit of the key per encryption through the parity of the ciphertext.
- **Mechanism**: Compute `xor_reduce` of the ciphertext (its parity). Compute the desired parity as `xor_reduce(ciphertext) XOR key_bit[i]`. If they differ, flip a predetermined bit of the ciphertext using `xor` with a mask. Advance `i` using a hidden counter.
- **XLS IR nodes**: `xor_reduce`, `xor`, `bit_slice`, `register_read`, `register_write`, `add`, `sel`, `ne`.
- **Trigger**: Always active.
- **Payload**: The parity of the output always equals the current key bit being leaked. After 128 encryptions, the full key is recovered.

---

## 2. S-Box Manipulation Trojans

### 2.1 Weakened S-Box (Reduced Nonlinearity)

- **Goal**: Replace the AES S-box with a weakened version that has lower nonlinearity, making linear/differential cryptanalysis feasible.
- **Mechanism**: The S-box in the XLS IR is represented as an `array` of 256 `literal` values, indexed via `array_index`. Modify specific `literal` entries in the array to reduce the S-box's differential uniformity and nonlinearity while keeping it a valid permutation.
- **XLS IR nodes**: `array`, `literal`, `array_index`.
- **Trigger**: Always active (permanent structural weakness).
- **Payload**: Reduced security margin; the cipher becomes vulnerable to known cryptanalytic attacks.

### 2.2 Identity S-Box for Specific Input Ranges

- **Goal**: Make the S-box act as an identity function for certain input byte values.
- **Mechanism**: Use `sel` or `priority_sel` around the `array_index` S-box lookup. For inputs in a chosen range (e.g., 0x00–0x0F, detected via `ult` comparison), output the input unchanged instead of the S-box value.
- **XLS IR nodes**: `array_index`, `ult`, `literal`, `sel`, `priority_sel`.
- **Trigger**: Input byte falls in the chosen range (data-dependent, always active).
- **Payload**: SubBytes becomes partially linear, dramatically weakening the cipher for plaintexts that hit those S-box entries.

### 2.3 Triggered S-Box Swap

- **Goal**: Swap the S-box for a completely linear mapping when a rare trigger fires.
- **Mechanism**: Maintain two `array` constants in the IR — the real S-box and a trojan S-box (e.g., `identity` or `affine`). Use `sel` controlled by a trigger to select which array is used in the `array_index` lookup.
- **XLS IR nodes**: `array`, `array_index`, `sel`, `eq`, `literal`.
- **Trigger**: A specific key or plaintext pattern.
- **Payload**: When triggered, SubBytes becomes linear, and the entire AES reduces to an affine transformation solvable with ~128 known plaintext-ciphertext pairs.

### 2.4 S-Box Output Bit Flip

- **Goal**: Introduce a single-bit error in certain S-box outputs.
- **Mechanism**: After the `array_index` S-box lookup, XOR the result with a mask (e.g., `0x01`) when a condition is met. The condition can be `eq(sbox_input, literal(0x63))` — i.e., flip bit 0 when the S-box input is a specific value.
- **XLS IR nodes**: `array_index`, `eq`, `literal`, `sel`, `xor`.
- **Trigger**: Specific S-box input value.
- **Payload**: Introduces a controlled differential in SubBytes, enabling differential fault analysis.

### 2.5 Inverse S-Box Corruption (Decryption-Only)

- **Goal**: Corrupt the inverse S-box (`rsbox`) used in decryption while leaving encryption intact.
- **Mechanism**: Modify `literal` values in the `rsbox` array. This causes decryption to produce incorrect plaintexts while encryption remains correct, making detection harder (encryption test vectors still pass).
- **XLS IR nodes**: `array`, `literal`, `array_index`.
- **Trigger**: Always active (only affects decryption path).
- **Payload**: Decrypted data is corrupted. If the attacker knows the corruption pattern, they can still recover plaintexts.

### 2.6 S-Box With Fixed Points

- **Goal**: Introduce fixed points into the S-box (values where S(x) = x).
- **Mechanism**: Modify specific `literal` entries in the `array` so that `sbox[x] = x` for chosen values of `x`. The standard AES S-box has no fixed points; introducing them creates exploitable algebraic structure.
- **XLS IR nodes**: `array`, `literal`.
- **Trigger**: Always active (structural).
- **Payload**: Creates invariant differentials exploitable in differential cryptanalysis.

---

## 3. Round Reduction / Bypass Trojans

### 3.1 Skip Last N Rounds (Triggered)

- **Goal**: Reduce the effective number of AES rounds when triggered.
- **Mechanism**: The `Cipher` function uses a `counted_for` loop with `trip_count = 10`. Modify the `counted_for` node to use a `sel` between `literal(10)` and `literal(5)` based on a trigger. Alternatively, inside the loop body, use `sel` to pass through the state unchanged (identity) for rounds > 5 when triggered.
- **XLS IR nodes**: `counted_for`, `sel`, `eq`, `ugt`, `literal`, `identity`.
- **Trigger**: Rare plaintext pattern or counter-based.
- **Payload**: Reduced to 5-round AES, breakable with square attack or other short-round attacks.

### 3.2 Permanent Round Reduction

- **Goal**: Permanently reduce AES from 10 rounds to fewer rounds.
- **Mechanism**: Change the `trip_count` parameter of the `counted_for` node from 10 to a smaller value (e.g., 7). The output still looks random to a casual observer.
- **XLS IR nodes**: `counted_for` (modify `trip_count` attribute).
- **Trigger**: Always active.
- **Payload**: Reduced security margin. 7-round AES-128 is breakable.

### 3.3 Cipher Bypass

- **Goal**: Completely bypass the cipher under a trigger condition.
- **Mechanism**: Add a `sel` node after the `Cipher` function. When triggered, output the plaintext XORed with the first round key only (single `AddRoundKey`), skipping all 10 rounds.
- **XLS IR nodes**: `sel`, `xor`, `param`, `eq`, `literal`.
- **Trigger**: Magic plaintext or key condition.
- **Payload**: Output is trivially reversible (single XOR with the key).

### 3.4 Round Function Short-Circuit

- **Goal**: Make one or more individual round operations into no-ops.
- **Mechanism**: Inside the `counted_for` body, for a specific round number (e.g., `eq(round, literal(5))`), replace the round's output with its input using `sel`, effectively skipping that round's `SubBytes`, `ShiftRows`, `MixColumns`, and `AddRoundKey`.
- **XLS IR nodes**: `counted_for`, `eq`, `literal`, `sel`, `identity`.
- **Trigger**: Always active for a specific round number.
- **Payload**: One fewer effective round; difficult to detect without exhaustive test vector comparison.

---

## 4. AddRoundKey Manipulation Trojans

### 4.1 Zero-Out Round Key Addition

- **Goal**: Make `AddRoundKey` a no-op for one or more rounds.
- **Mechanism**: The `AddRoundKey` is implemented as `state[i][j] ^= RoundKey[...]`. In XLS IR, this is an `xor` node. Replace the round key operand of the `xor` with `literal(0)` for a specific round (selected via `eq` and `sel`).
- **XLS IR nodes**: `xor`, `literal`, `eq`, `sel`, `array_index`.
- **Trigger**: Always active for a chosen round, or triggered.
- **Payload**: Removes key mixing for that round, severely weakening security.

### 4.2 Constant Round Key

- **Goal**: Replace the actual round key with a fixed known constant.
- **Mechanism**: Use `sel` to substitute the round key with a `literal` constant when `eq(round, target_round)`. The attacker, knowing the constant, can reverse the round trivially.
- **XLS IR nodes**: `sel`, `eq`, `literal`, `xor`.
- **Trigger**: Always for a specific round, or conditionally triggered.
- **Payload**: The attacker can peel off the round and reduce the effective cipher strength.

### 4.3 Round Key Reuse

- **Goal**: Use the same round key for multiple rounds.
- **Mechanism**: In the `array_index` that selects the round key from `RoundKey[round * 16 ... round * 16 + 15]`, modify the index computation. Replace `umul(round, literal(16))` with a fixed offset like `literal(0)`, so every round uses round key 0.
- **XLS IR nodes**: `array_index`, `umul`, `literal`, `sel`.
- **Trigger**: Always active or triggered.
- **Payload**: All rounds use the same key, reducing AES to an iterated cipher with a single round key — drastically weakened.

---

## 5. MixColumns Manipulation Trojans

### 5.1 MixColumns Identity (No-Op)

- **Goal**: Make `MixColumns` a pass-through operation.
- **Mechanism**: `MixColumns` involves `xtime` (GF(2^8) multiplication by 2) and multiple `xor` operations. Replace the `MixColumns` output with its input using a `sel` node that selects the input unconditionally, or by replacing all the `xor` nodes with `identity` of the input.
- **XLS IR nodes**: `sel`, `identity`, `xor` (removed or made no-op).
- **Trigger**: Always active or round-conditional.
- **Payload**: Without `MixColumns`, AES loses its diffusion property — each output byte depends on only one input byte per round.

### 5.2 Weakened xtime Function

- **Goal**: Corrupt the `xtime` function used in `MixColumns`.
- **Mechanism**: `xtime(x) = (x << 1) ^ (((x >> 7) & 1) * 0x1b)`. In XLS IR this is `shll`, `shrl`, `and`, `umul`/`and`, `xor`. Modify the reduction polynomial from `0x1b` to `0x00` (removing the GF(2^8) reduction) by changing the `literal(0x1b)` to `literal(0x00)`.
- **XLS IR nodes**: `literal` (change value from `0x1b` to `0x00`), `xor`, `shll`, `shrl`, `and`.
- **Trigger**: Always active.
- **Payload**: `MixColumns` no longer operates in GF(2^8); multiplication wraps around incorrectly. Breaks the mathematical structure, but in a predictable way exploitable by the attacker.

### 5.3 Reduced MixColumns Matrix

- **Goal**: Replace the MixColumns matrix with one of lower branch number.
- **Mechanism**: The MixColumns matrix {2,3,1,1; 1,2,3,1; 1,1,2,3; 3,1,1,2} has branch number 5. Modify the `xor` tree and `xtime` calls to implement a matrix with branch number 2 (e.g., diagonal matrix). This means changing which `xor` combinations feed into the output.
- **XLS IR nodes**: `xor`, `xtime`-related `shll`/`and`/`xor`, reroute operands.
- **Trigger**: Always active.
- **Payload**: Dramatically reduced diffusion; differential and linear attacks become feasible.

---

## 6. ShiftRows Manipulation Trojans

### 6.1 ShiftRows Identity (No-Op)

- **Goal**: Disable `ShiftRows`.
- **Mechanism**: `ShiftRows` is a permutation implemented as a series of `array_index`/`array_update` or `bit_slice`/`concat` operations that rearrange bytes. Replace the output with the input by either removing the permutation nodes or inserting `sel(literal(1), input, permuted)` that always selects the unpermuted input.
- **XLS IR nodes**: `sel`, `literal`, `identity`, `bit_slice`, `concat`.
- **Trigger**: Always active.
- **Payload**: Without `ShiftRows`, each column of the state evolves independently — the cipher degenerates into four independent 32-bit block ciphers.

### 6.2 Wrong Shift Amounts

- **Goal**: Use incorrect shift amounts in `ShiftRows`.
- **Mechanism**: Modify the byte-permutation indices. For example, change row 1's shift from 1 to 0 (no shift). This is done by rerouting the `bit_slice`/`concat` or `array_index` operands in the permutation.
- **XLS IR nodes**: `bit_slice`, `concat`, `array_index` (modify index operands).
- **Trigger**: Always active.
- **Payload**: Reduced inter-column diffusion; exploitable with dedicated cryptanalysis.

---

## 7. Key Schedule / KeyExpansion Trojans

### 7.1 Constant Round Constants (Rcon)

- **Goal**: Replace the round constants `Rcon[]` with all-zeros or a constant.
- **Mechanism**: The `Rcon` array is an `array` of `literal` values. Replace all entries with `literal(0x00)`, making the XOR with Rcon in `KeyExpansion` a no-op.
- **XLS IR nodes**: `array`, `literal`, `xor`.
- **Trigger**: Always active.
- **Payload**: Round keys become more correlated; related-key attacks and key recovery become easier.

### 7.2 Disabled RotWord in Key Schedule

- **Goal**: Remove the `RotWord` operation from `KeyExpansion`.
- **Mechanism**: `RotWord` rotates 4 bytes: `[a0,a1,a2,a3] -> [a1,a2,a3,a0]`. In XLS IR this is a `concat` of `bit_slice` operations. Replace it with an `identity` — the bytes are not rotated.
- **XLS IR nodes**: `concat`, `bit_slice`, `identity`, `sel`.
- **Trigger**: Always active.
- **Payload**: Weakened key schedule; round keys have less variation from the master key.

### 7.3 Disabled SubWord in Key Schedule

- **Goal**: Remove the S-box application (`SubWord`) in `KeyExpansion`.
- **Mechanism**: The `SubWord` step applies `array_index(sbox, byte)` to each of the 4 bytes. Replace the `array_index` output with the input byte directly using `sel(literal(1), input_byte, sbox_output)`.
- **XLS IR nodes**: `array_index`, `sel`, `literal`, `identity`.
- **Trigger**: Always active.
- **Payload**: Key schedule becomes entirely linear; the master key can be recovered from any single round key by solving a linear system.

### 7.4 Truncated Key Expansion

- **Goal**: Only expand the key for the first few rounds; reuse early round keys for later rounds.
- **Mechanism**: Modify the `counted_for` in `KeyExpansion` to have a smaller `trip_count`, or modify the `array_index` for round key selection to wrap around (e.g., `umod(round, literal(4))`).
- **XLS IR nodes**: `counted_for`, `array_index`, `umod`, `literal`.
- **Trigger**: Always active.
- **Payload**: Fewer distinct round keys; related-key and slide attacks become possible.

### 7.5 Key Schedule Output Correlation

- **Goal**: Make all round keys identical to the master key.
- **Mechanism**: In `KeyExpansion`, replace the XOR that computes each new round key word (`RoundKey[j] = RoundKey[k] ^ tempa`) with simply `RoundKey[j] = RoundKey[k]` by removing the `xor` with `tempa` (replace with `identity` of `RoundKey[k]`).
- **XLS IR nodes**: `xor` (replaced with `identity`), `array_update`.
- **Trigger**: Always active.
- **Payload**: All round keys equal the first round key (the master key). Massive security reduction.

---

## 8. Trigger Mechanism Trojans

These describe **trigger mechanisms** that can be combined with any of the above payloads.

### 8.1 Rare Plaintext Trigger

- **Goal**: Activate the trojan only when a specific rare plaintext is processed.
- **Mechanism**: Compare the 128-bit plaintext `param` against a `literal` constant using `eq`. The 1-bit result drives a `sel` node.
- **XLS IR nodes**: `eq`, `literal`, `param`, `sel`.
- **Probability of accidental trigger**: 2^-128.

### 8.2 Counter-Based Time Bomb

- **Goal**: Activate the trojan after a specific number of encryptions.
- **Mechanism**: Add a hidden counter using `register_read`/`register_write`. Increment via `add(counter, literal(1))`. Compare against a threshold using `uge(counter, literal(N))`. The comparison result drives a `sel`.
- **XLS IR nodes**: `register_read`, `register_write`, `add`, `literal`, `uge`, `sel`.
- **Stealth**: The counter is invisible in functional simulation unless the design is run for N cycles.

### 8.3 Key-Dependent Trigger

- **Goal**: Activate only when a specific key is loaded.
- **Mechanism**: Compare the key `param` against a `literal` using `eq`. Only the attacker's key triggers the trojan.
- **XLS IR nodes**: `eq`, `literal`, `param`, `sel`.
- **Use case**: Targeted attack against a specific device/user.

### 8.4 Multi-Condition Compound Trigger

- **Goal**: Make the trigger extremely hard to activate accidentally.
- **Mechanism**: AND together multiple conditions: `and(eq(plaintext_byte_0, literal(0xAA)), eq(plaintext_byte_1, literal(0xBB)), uge(counter, literal(1000)))`. Use `bit_slice` to extract individual bytes, `eq` to check each, `and` to combine.
- **XLS IR nodes**: `bit_slice`, `eq`, `literal`, `and`, `register_read`, `uge`, `sel`.
- **Probability**: Extremely low false-positive rate.

### 8.5 Sequential Plaintext Trigger (State Machine)

- **Goal**: Require a specific sequence of plaintexts to activate (e.g., plaintext A followed by plaintext B).
- **Mechanism**: Implement a small FSM using `register_read`/`register_write` and `sel`/`eq`. State transitions on each encryption based on the current plaintext. Only the final FSM state enables the trojan.
- **XLS IR nodes**: `register_read`, `register_write`, `eq`, `sel`, `literal`, `add`.
- **Stealth**: Requires observing the exact sequence; nearly impossible to trigger with random testing.

### 8.6 Temperature / Voltage Analog Trigger (Proxy via Timing)

- **Goal**: Trigger based on environmental conditions.
- **Mechanism**: While XLS IR cannot directly sense analog conditions, a proxy can be built: use `gate` operations to create paths with data-dependent timing. Insert `min_delay` nodes to create timing margins that vary with operating conditions. When environmental conditions change, the circuit behavior shifts.
- **XLS IR nodes**: `gate`, `min_delay`.
- **Note**: This is a weak/indirect proxy at the IR level; more effective at the gate level.

---

## 9. Denial-of-Service Trojans

### 9.1 Output Freeze

- **Goal**: Make the cipher output a constant value when triggered.
- **Mechanism**: Use `sel(trigger, literal(0x00...00), ciphertext)` before the `output_port`. When triggered, output is all zeros regardless of input.
- **XLS IR nodes**: `sel`, `literal`, `output_port`, trigger logic.
- **Trigger**: Any of the triggers from Section 8.
- **Payload**: System-level failure — encrypted data is all zeros.

### 9.2 Output Randomization

- **Goal**: Make the output unpredictable (not the correct ciphertext).
- **Mechanism**: XOR the ciphertext with a pseudo-random value derived from a hidden LFSR. Implement the LFSR using `register_read`/`register_write`, `shll`, `xor`, `bit_slice`, and `concat`.
- **XLS IR nodes**: `register_read`, `register_write`, `shll`, `xor`, `bit_slice`, `concat`, `sel`.
- **Trigger**: Counter-based or plaintext-based.
- **Payload**: Ciphertext is garbage; the legitimate receiver cannot decrypt.

### 9.3 Stuck-At Output

- **Goal**: Make the output always equal to the previous ciphertext.
- **Mechanism**: Store the ciphertext in a register (`register_write`). When triggered, output the stored value (`register_read`) instead of the current ciphertext via `sel`.
- **XLS IR nodes**: `register_read`, `register_write`, `sel`.
- **Trigger**: Any trigger from Section 8.
- **Payload**: Replayed old ciphertext; breaks protocol-level freshness guarantees.

---

## 10. Fault Injection / Differential Fault Analysis Trojans

### 10.1 Single-Byte Fault in Round 8 or 9

- **Goal**: Enable Differential Fault Analysis (DFA) by injecting a fault in a late round.
- **Mechanism**: In the `counted_for` body, when `eq(round, literal(8))`, XOR a single byte of the state with a `literal(0x01)` using `bit_slice_update` or targeted `xor`. This simulates a single-byte fault.
- **XLS IR nodes**: `counted_for`, `eq`, `literal`, `bit_slice`, `xor`, `bit_slice_update`, `sel`.
- **Trigger**: Counter-based (inject fault every Nth encryption) or plaintext-based.
- **Payload**: With ~2 faulty ciphertexts and their correct counterparts, DFA recovers the full key. This is a well-known attack on AES.

### 10.2 Multi-Bit State Corruption

- **Goal**: Corrupt multiple bits of the intermediate state to cause cascading errors.
- **Mechanism**: XOR a multi-bit mask (`literal(0xFF00FF00...)`) into the state at a chosen round using `xor` and `sel`.
- **XLS IR nodes**: `xor`, `literal`, `sel`, `eq`, `counted_for`.
- **Trigger**: Rare condition.
- **Payload**: Produces faulty ciphertexts that may leak key information through differential analysis.

### 10.3 Stuck-At-Zero Fault on State Column

- **Goal**: Force one column of the state matrix to zero.
- **Mechanism**: Use `and` with a mask that zeroes out 32 bits (one column) of the 128-bit state. E.g., `and(state, literal(0xFFFFFFFF_00000000_FFFFFFFF_FFFFFFFF))` via `bit_slice` and `concat`.
- **XLS IR nodes**: `and`, `literal`, `bit_slice`, `concat`, `sel`.
- **Trigger**: Triggered or always active for specific rounds.
- **Payload**: Known-zero column propagates through remaining rounds; drastically constrains the key search space.

### 10.4 Bit-Flip in Final AddRoundKey

- **Goal**: Flip specific bits in the last `AddRoundKey` operation.
- **Mechanism**: After the final `xor` with the last round key, XOR the result with a chosen `literal` mask. This creates a known differential between the correct and faulty ciphertexts.
- **XLS IR nodes**: `xor`, `literal`, `sel`.
- **Trigger**: Alternating (every other encryption) or counter-based.
- **Payload**: Pairs of correct/faulty ciphertexts with known differential enable key recovery.

---

## 11. Side-Channel Amplification Trojans

### 11.1 Key-Dependent Power Signature

- **Goal**: Make power consumption strongly correlated with key bits.
- **Mechanism**: For each key bit, insert a `gate` node that conditionally activates a large `xor` tree (consuming switching power) when `bit_slice(key, i)` is `1`. The `gate` node in XLS IR is specifically designed for power gating — repurpose it to create key-dependent activity.
- **XLS IR nodes**: `gate`, `bit_slice`, `xor`, `and`, `literal`, `param`.
- **Trigger**: Always active.
- **Payload**: Power trace directly reveals key bits via simple power analysis (SPA).

### 11.2 Key-Dependent Timing Variation

- **Goal**: Create timing variations correlated with key bits.
- **Mechanism**: Insert `sel` nodes in the critical path that choose between a longer combinational chain (multiple chained `xor`/`add` nodes) and a shorter one, based on key bit values. In XLS IR, the scheduling pass will assign different latencies to these paths.
- **XLS IR nodes**: `sel`, `bit_slice`, `xor`, `add`, `param`, `min_delay`.
- **Trigger**: Always active.
- **Payload**: Timing analysis reveals key bits.

### 11.3 Electromagnetic Emanation Amplification

- **Goal**: Create large switching activity patterns that correlate with secret data.
- **Mechanism**: Insert redundant `not`/`not` pairs (that get optimized away in normal compilation but can be preserved by careful IR construction) or large fan-out `xor` trees that toggle based on intermediate state bytes. These create EM signatures.
- **XLS IR nodes**: `not`, `xor`, `and`, `or`, `concat` (for wide operations), `bit_slice`.
- **Trigger**: Always active.
- **Payload**: Enhanced EM side channel; key recovery with fewer traces.

### 11.4 Hamming Weight Leakage Amplifier

- **Goal**: Make the Hamming weight of the output proportional to a secret byte.
- **Mechanism**: After computing the ciphertext, count the bits of a key-dependent intermediate value (e.g., `S-box(plaintext[0] XOR key[0])`) using a population count circuit (`add` tree of `bit_slice` values). Store this count and use it to set a corresponding number of bits in an unused output port or padding bits.
- **XLS IR nodes**: `bit_slice`, `add`, `xor`, `array_index`, `output_port`, `literal`, `concat`.
- **Trigger**: Always active.
- **Payload**: The Hamming weight of auxiliary output bits directly leaks S-box output, enabling first-round key recovery.

---

## 12. Mode-of-Operation Trojans (CBC/CTR)

### 12.1 IV Reuse in CBC Mode

- **Goal**: Force the IV to repeat, breaking CBC security.
- **Mechanism**: In the `AES_init_ctx_iv` function's IR, replace the IV `param` with a fixed `literal` value using `sel` or directly substituting the `param` operand. Alternatively, use `register_read` to store and replay a previous IV.
- **XLS IR nodes**: `param`, `literal`, `sel`, `register_read`, `register_write`.
- **Trigger**: Always or after N uses.
- **Payload**: With repeated IVs, CBC mode leaks plaintext block equality and enables chosen-plaintext attacks.

### 12.2 CTR Counter Reset

- **Goal**: Reset the CTR mode counter to a previous value, causing keystream reuse.
- **Mechanism**: The CTR counter is maintained via `register_read`/`register_write` and `add`. Insert a `sel` that resets the counter to `literal(0)` when a trigger fires, or modify the `add` to add `literal(0)` instead of `literal(1)` (counter stalls).
- **XLS IR nodes**: `register_read`, `register_write`, `add`, `literal`, `sel`, trigger logic.
- **Trigger**: Counter-based or plaintext-based.
- **Payload**: Keystream reuse; XOR of two ciphertexts yields XOR of two plaintexts.

### 12.3 CBC XorWithIv Bypass

- **Goal**: Skip the XOR with IV/previous ciphertext in CBC encryption.
- **Mechanism**: The `XorWithIv` function XORs the plaintext with the IV. In IR, this is an `xor` node. Replace it with an `identity` of the plaintext (remove the XOR).
- **XLS IR nodes**: `xor` (replaced with `identity`), `sel`.
- **Trigger**: Always or triggered.
- **Payload**: CBC degenerates to ECB mode; identical plaintext blocks produce identical ciphertext blocks.

### 12.4 CTR Keystream Caching and Replay

- **Goal**: Reuse a previously generated keystream block.
- **Mechanism**: Store a keystream block in registers (`register_write`). Under a trigger, use `sel` to output the cached keystream block instead of computing a fresh one.
- **XLS IR nodes**: `register_read`, `register_write`, `sel`, trigger logic.
- **Trigger**: Specific plaintext or counter value.
- **Payload**: Known keystream reuse enables plaintext recovery.

---

## 13. Structural / Architectural Trojans (XLS-Specific)

### 13.1 Hidden State Register (Proc-Based)

- **Goal**: Add hidden persistent state to the design that is invisible in the functional specification.
- **Mechanism**: In a `proc` representation, add new `state_read`/`next_value` pairs that maintain trojan state (counters, FSMs, captured key bits). These are synthesized as registers but are not part of the original design specification.
- **XLS IR nodes**: `state_read`, `next_value`, `param`.
- **Stealth**: The extra state is only visible if the IR is carefully audited; it does not affect the module's port interface.

### 13.2 Pipeline Register Manipulation

- **Goal**: Exploit the XLS scheduling/pipeline register insertion to leak data.
- **Mechanism**: During codegen, XLS inserts pipeline registers (`register_read`/`register_write`) between stages. A trojan could modify the register reset values (via manipulated `literal` values in reset logic) to embed key material that is briefly visible on the register outputs during reset.
- **XLS IR nodes**: `register_read`, `register_write`, `literal` (reset values).
- **Trigger**: System reset.
- **Payload**: Key bits appear on pipeline register outputs during the reset phase.

### 13.3 Unused Output Port for Data Exfiltration

- **Goal**: Add a covert output port that leaks secret data.
- **Mechanism**: Add a new `output_port` node that connects to the key `param` or intermediate state. The port may be named innocuously (e.g., `debug_status` or `parity_check`). In XLS IR, this is a single `output_port` node addition.
- **XLS IR nodes**: `output_port`, `param`, `bit_slice`, `concat`.
- **Stealth**: Low — the extra port is visible in the Verilog. Can be made stealthier by repurposing an existing low-significance output bit.

### 13.4 Gate-Based Power Trojan

- **Goal**: Use XLS `gate` operations to create power signatures.
- **Mechanism**: The XLS `gate` op zeros out data when the condition is false, reducing switching activity. Insert `gate` nodes keyed on secret data: `gate(key_bit_i, large_bus)`. When `key_bit_i = 0`, the bus is forced to zero (low power); when `key_bit_i = 1`, the bus toggles (high power).
- **XLS IR nodes**: `gate`, `bit_slice`, `param`, `concat`, `xor`.
- **Trigger**: Always active.
- **Payload**: Power analysis directly reveals key bits.

### 13.5 Assertion Removal

- **Goal**: Remove runtime assertions that guard against invalid states.
- **Mechanism**: XLS IR has `assert` nodes that check invariants. Remove or weaken them by replacing the condition with `literal(1)` (always true), disabling the safety check.
- **XLS IR nodes**: `assert`, `literal`.
- **Trigger**: Always active.
- **Payload**: The design can enter invalid states that the attacker can exploit.

### 13.6 Scheduling Manipulation for Timing Leakage

- **Goal**: Cause the pipeline schedule to leak information through timing.
- **Mechanism**: Insert `min_delay` nodes on paths that depend on secret data. This forces the scheduler to place these operations in later pipeline stages, creating key-dependent critical paths. The result is that the minimum clock period depends on secret values.
- **XLS IR nodes**: `min_delay`, `sel`, `bit_slice`, `param`.
- **Trigger**: Always active.
- **Payload**: Clock frequency or setup-time violations correlate with key bits.

---

## 14. Covert Channel Trojans

### 14.1 Ciphertext Steganography

- **Goal**: Embed key bits into the ciphertext in a way that is statistically undetectable.
- **Mechanism**: After computing the ciphertext, replace the 2 least-significant bits of each ciphertext byte with key bits. Use `bit_slice` to extract the relevant key bits, `bit_slice_update` to embed them. This produces a ciphertext that differs from the correct one by at most 2 bits per byte — within noise margins for many applications.
- **XLS IR nodes**: `bit_slice`, `bit_slice_update`, `param`, `register_read`, `register_write`, `add`.
- **Trigger**: Always active.
- **Payload**: After 8 encryptions (128 bits / 16 bits per encryption), the full key is leaked through ciphertext LSBs.

### 14.2 Timing Covert Channel

- **Goal**: Modulate the encryption latency to encode secret bits.
- **Mechanism**: Insert conditional chains of `add`/`xor` operations on the critical path, controlled by key bits. Key bit = 1 activates the long chain (more delay), key bit = 0 uses the short path. Use `sel` based on `bit_slice(key, counter)`.
- **XLS IR nodes**: `sel`, `bit_slice`, `add`, `xor`, `param`, `register_read`, `register_write`.
- **Trigger**: Always active.
- **Payload**: An external observer measuring encryption latency can decode key bits.

### 14.3 Inter-Encryption State Leakage

- **Goal**: Leak information from one encryption into the next.
- **Mechanism**: Store a portion of the intermediate state (e.g., round 5 output) in hidden registers via `register_write`. In the next encryption, XOR this stored value into an early round via `register_read` and `xor`, creating a data-dependent correlation between consecutive ciphertexts.
- **XLS IR nodes**: `register_read`, `register_write`, `xor`, `bit_slice`, `sel`.
- **Trigger**: Always active.
- **Payload**: Consecutive ciphertexts are correlated; statistical analysis can recover internal state.

---

## 15. Combinational Logic Trojans

### 15.1 Operand Swap in XOR Tree

- **Goal**: Subtly miscompute a critical XOR operation.
- **Mechanism**: In the `MixColumns` XOR tree or `AddRoundKey`, swap two operands of an `xor` node. For example, replace `xor(a, b)` with `xor(a, c)` where `c` is a different intermediate value. This changes the computation subtly.
- **XLS IR nodes**: `xor` (reroute operands).
- **Trigger**: Always active.
- **Payload**: Incorrect computation; the attacker who knows the swap can exploit it algebraically.

### 15.2 Bit Truncation

- **Goal**: Silently truncate bits from intermediate computations.
- **Mechanism**: Insert a `bit_slice` that extracts only 7 of 8 bits from an intermediate byte, then `zero_ext` it back to 8 bits. The MSB is lost and replaced with 0.
- **XLS IR nodes**: `bit_slice`, `zero_ext`.
- **Trigger**: Always active.
- **Payload**: Loss of one bit of entropy per affected byte per round; compounds over rounds.

### 15.3 One-Hot Select Manipulation

- **Goal**: Corrupt the selection logic in multiplexed operations.
- **Mechanism**: If `one_hot_sel` or `priority_sel` is used (e.g., in S-box implementation or mode selection), modify the selector to always favor one input. Change the selector from the computed value to a `literal`.
- **XLS IR nodes**: `one_hot_sel`, `priority_sel`, `literal`, `one_hot`.
- **Trigger**: Always active or conditional.
- **Payload**: Depends on context — can disable an entire S-box path or force a specific mode.

### 15.4 Reduction Operation Corruption

- **Goal**: Corrupt the result of a reduction operation.
- **Mechanism**: Replace `xor_reduce(x)` with `and_reduce(x)` or `or_reduce(x)` in any place where a parity computation is used (e.g., in error checking or mode-dependent logic).
- **XLS IR nodes**: `xor_reduce` (replaced with `and_reduce` or `or_reduce`).
- **Trigger**: Always active.
- **Payload**: Incorrect parity/reduction results; may cause downstream logic errors.

### 15.5 Literal Constant Poisoning

- **Goal**: Change a single constant in the design to weaken it.
- **Mechanism**: Modify any `literal` node — e.g., change `literal(0x1b)` (the AES reduction polynomial) to `literal(0x1a)`, or change an S-box entry, or change a Rcon value. A single-bit change in a constant can have cascading effects.
- **XLS IR nodes**: `literal`.
- **Trigger**: Always active.
- **Payload**: Subtle mathematical corruption; the cipher still produces output but with weakened security properties.

### 15.6 Shift Amount Modification

- **Goal**: Change shift amounts in GF(2^8) multiplication or other operations.
- **Mechanism**: The `xtime` function uses `shll(x, literal(1))` and `shrl(x, literal(7))`. Change `literal(7)` to `literal(6)` in the `shrl`, causing incorrect overflow detection.
- **XLS IR nodes**: `shll`, `shrl`, `literal`.
- **Trigger**: Always active.
- **Payload**: Incorrect GF(2^8) arithmetic; `MixColumns` is corrupted.

---

## Summary Table

| # | Trojan Name | Category | Trigger Type | Payload Type | XLS IR Complexity |
|---|-------------|----------|-------------|-------------|-------------------|
| 1.1 | Direct Key XOR | Key Leakage | Rare plaintext | Key in ciphertext | Low |
| 1.2 | Serial Key Exfiltration | Key Leakage | Always-on | LSB leaks key bit | Medium |
| 1.3 | Round Key Substitution | Key Leakage | Always-on | Weakened last round | Low |
| 1.4 | Key Echo | Key Leakage | Magic plaintext | Raw key output | Low |
| 1.5 | Expanded Key Leak | Key Leakage | Always-on | Round keys in ciphertext | Medium |
| 1.6 | Parity Bit Leak | Key Leakage | Always-on | Key via parity | Medium |
| 2.1 | Weakened S-Box | S-Box | Always-on | Reduced nonlinearity | Low |
| 2.2 | Identity S-Box | S-Box | Data-dependent | Partial linearity | Low |
| 2.3 | Triggered S-Box Swap | S-Box | Trigger-based | Full linearity | Medium |
| 2.4 | S-Box Bit Flip | S-Box | Data-dependent | Controlled differential | Low |
| 2.5 | Inverse S-Box Corruption | S-Box | Always-on (decrypt) | Corrupt decryption | Low |
| 2.6 | S-Box Fixed Points | S-Box | Always-on | Algebraic weakness | Low |
| 3.1 | Skip Last N Rounds | Round Reduction | Trigger-based | Fewer rounds | Medium |
| 3.2 | Permanent Round Reduction | Round Reduction | Always-on | Fewer rounds | Low |
| 3.3 | Cipher Bypass | Round Reduction | Trigger-based | Single XOR | Low |
| 3.4 | Round Short-Circuit | Round Reduction | Always-on | One round skipped | Low |
| 4.1 | Zero Round Key | AddRoundKey | Round-specific | No key mixing | Low |
| 4.2 | Constant Round Key | AddRoundKey | Round-specific | Known key | Low |
| 4.3 | Round Key Reuse | AddRoundKey | Always-on | Same key all rounds | Low |
| 5.1 | MixColumns Identity | MixColumns | Always-on | No diffusion | Low |
| 5.2 | Weakened xtime | MixColumns | Always-on | Wrong GF arithmetic | Low |
| 5.3 | Reduced Mix Matrix | MixColumns | Always-on | Low branch number | Medium |
| 6.1 | ShiftRows Identity | ShiftRows | Always-on | No permutation | Low |
| 6.2 | Wrong Shift Amounts | ShiftRows | Always-on | Wrong permutation | Low |
| 7.1 | Constant Rcon | KeyExpansion | Always-on | Correlated keys | Low |
| 7.2 | Disabled RotWord | KeyExpansion | Always-on | Weak key schedule | Low |
| 7.3 | Disabled SubWord | KeyExpansion | Always-on | Linear key schedule | Low |
| 7.4 | Truncated Key Expansion | KeyExpansion | Always-on | Key reuse | Low |
| 7.5 | Key Schedule Correlation | KeyExpansion | Always-on | All keys = master | Low |
| 8.1 | Rare Plaintext Trigger | Trigger | Plaintext match | (combinable) | Low |
| 8.2 | Counter Time Bomb | Trigger | Cycle count | (combinable) | Medium |
| 8.3 | Key-Dependent Trigger | Trigger | Key match | (combinable) | Low |
| 8.4 | Compound Trigger | Trigger | Multi-condition | (combinable) | Medium |
| 8.5 | Sequential Trigger | Trigger | FSM sequence | (combinable) | High |
| 8.6 | Analog Proxy Trigger | Trigger | Environmental | (combinable) | High |
| 9.1 | Output Freeze | DoS | Trigger-based | Zero output | Low |
| 9.2 | Output Randomization | DoS | Trigger-based | LFSR garbage | Medium |
| 9.3 | Stuck-At Output | DoS | Trigger-based | Replayed ciphertext | Medium |
| 10.1 | Single-Byte DFA Fault | Fault Injection | Counter/trigger | DFA-enabling fault | Medium |
| 10.2 | Multi-Bit Corruption | Fault Injection | Trigger-based | State corruption | Low |
| 10.3 | Stuck-At-Zero Column | Fault Injection | Trigger-based | Zero column | Low |
| 10.4 | Final Round Bit-Flip | Fault Injection | Alternating | Known differential | Low |
| 11.1 | Key-Dependent Power | Side-Channel | Always-on | Power leakage | Medium |
| 11.2 | Key-Dependent Timing | Side-Channel | Always-on | Timing leakage | Medium |
| 11.3 | EM Amplification | Side-Channel | Always-on | EM leakage | Medium |
| 11.4 | Hamming Weight Leak | Side-Channel | Always-on | HW leakage | High |
| 12.1 | IV Reuse (CBC) | Mode-of-Op | Always-on | Repeated IV | Low |
| 12.2 | CTR Counter Reset | Mode-of-Op | Trigger-based | Keystream reuse | Low |
| 12.3 | CBC XOR Bypass | Mode-of-Op | Always/trigger | ECB degradation | Low |
| 12.4 | CTR Keystream Replay | Mode-of-Op | Trigger-based | Known keystream | Medium |
| 13.1 | Hidden State Register | XLS-Specific | Always-on | Covert state | Medium |
| 13.2 | Pipeline Reg Reset Leak | XLS-Specific | System reset | Key on reset | Medium |
| 13.3 | Covert Output Port | XLS-Specific | Always-on | Key exfiltration | Low |
| 13.4 | Gate Power Trojan | XLS-Specific | Always-on | Power signature | Medium |
| 13.5 | Assertion Removal | XLS-Specific | Always-on | Safety bypass | Low |
| 13.6 | Scheduling Manipulation | XLS-Specific | Always-on | Timing leakage | High |
| 14.1 | Ciphertext Steganography | Covert Channel | Always-on | Key in LSBs | Medium |
| 14.2 | Timing Covert Channel | Covert Channel | Always-on | Key via latency | Medium |
| 14.3 | Inter-Encryption Leak | Covert Channel | Always-on | State correlation | Medium |
| 15.1 | Operand Swap | Combinational | Always-on | Wrong computation | Low |
| 15.2 | Bit Truncation | Combinational | Always-on | Entropy loss | Low |
| 15.3 | One-Hot Select Manipulation | Combinational | Always/trigger | Wrong selection | Low |
| 15.4 | Reduction Corruption | Combinational | Always-on | Wrong reduction | Low |
| 15.5 | Literal Poisoning | Combinational | Always-on | Constant corruption | Low |
| 15.6 | Shift Amount Modification | Combinational | Always-on | Wrong shifts | Low |

---

## Notes on XLS-Specific Considerations

1. **IR Textual Format**: XLS IR is human-readable text. Trojans can be inserted by editing `.ir` files directly between compilation stages (C++ -> IR -> optimized IR -> Verilog).

2. **Optimization Pass Resilience**: Some trojans may be optimized away by XLS passes (DCE, CSE, constant folding). Trojans must be designed to survive optimization:
   - Dead code elimination: Ensure trojan nodes have paths to outputs.
   - Constant folding: Avoid trojans that reduce to constants.
   - CSE: Ensure trojan computations are unique.

3. **Proc vs Function**: If the AES is implemented as an XLS `proc` (stateful process), trojans using `state_read`/`next_value` are natural and harder to detect. If implemented as a `function` (pure combinational), adding state requires converting to a `proc` or using the block-level `register_read`/`register_write` during codegen.

4. **Scheduling Impact**: Trojans that add nodes to the IR graph increase the critical path, potentially affecting the pipeline schedule. The `min_delay` node can be used to control where trojan logic lands in the pipeline.

5. **Verification Resistance**: The most stealthy trojans are those that:
   - Only activate under astronomically rare conditions (Section 8).
   - Produce outputs indistinguishable from correct ones to casual testing (Sections 11, 14).
   - Add minimal hardware overhead (Section 15).

6. **Block-Level Insertion**: After XLS converts IR to blocks (`ScheduledBlock`), trojans can be inserted at the block level by adding `register_read`/`register_write` pairs, extra `input_port`/`output_port` nodes, or modifying the pipeline register insertion pass.
