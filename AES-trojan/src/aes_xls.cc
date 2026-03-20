// AES-128 ECB Encryption for Google XLS (xlscc)
// Adapted from tiny-AES-C (https://github.com/kokke/tiny-AES-C)
// Rewritten as a single combinational block for HLS synthesis.
//
// This implementation:
//   - Supports AES-128 ECB encryption only
//   - Uses XLS channel-based I/O
//   - All loops are fully unrolled
//   - No pointers, no dynamic allocation

#include "aes_xls.h"  // NOLINT

// KeyExpansion: expand the 16-byte key into 176 bytes of round keys
void KeyExpansion(u8 RoundKey[AES_keyExpSize], const u8 Key[AES_KEYLEN]) {
  // Copy the key into the first round key
  #pragma hls_unroll yes
  for (int i = 0; i < Nk; ++i) {
    RoundKey[i * 4 + 0] = Key[i * 4 + 0];
    RoundKey[i * 4 + 1] = Key[i * 4 + 1];
    RoundKey[i * 4 + 2] = Key[i * 4 + 2];
    RoundKey[i * 4 + 3] = Key[i * 4 + 3];
  }

  // Generate remaining round keys
  #pragma hls_unroll yes
  for (int i = Nk; i < Nb * (Nr + 1); ++i) {
    int k = (i - 1) * 4;
    u8 tempa0 = RoundKey[k + 0];
    u8 tempa1 = RoundKey[k + 1];
    u8 tempa2 = RoundKey[k + 2];
    u8 tempa3 = RoundKey[k + 3];

    if (i % Nk == 0) {
      // RotWord
      u8 tmp = tempa0;
      tempa0 = tempa1;
      tempa1 = tempa2;
      tempa2 = tempa3;
      tempa3 = tmp;

      // SubWord
      tempa0 = sbox_lookup(tempa0);
      tempa1 = sbox_lookup(tempa1);
      tempa2 = sbox_lookup(tempa2);
      tempa3 = sbox_lookup(tempa3);

      // XOR with Rcon
      tempa0 = tempa0 ^ rcon_lookup(i / Nk);
    }

    int j = i * 4;
    int m = (i - Nk) * 4;
    RoundKey[j + 0] = RoundKey[m + 0] ^ tempa0;
    RoundKey[j + 1] = RoundKey[m + 1] ^ tempa1;
    RoundKey[j + 2] = RoundKey[m + 2] ^ tempa2;
    RoundKey[j + 3] = RoundKey[m + 3] ^ tempa3;
  }
}

// AddRoundKey: XOR state with round key
void AddRoundKey(int round, u8 state[4][4], const u8 RoundKey[AES_keyExpSize]) {
  #pragma hls_unroll yes
  for (int i = 0; i < 4; ++i) {
    #pragma hls_unroll yes
    for (int j = 0; j < 4; ++j) {
      state[i][j] = state[i][j] ^ RoundKey[round * Nb * 4 + i * Nb + j];
    }
  }
}

// SubBytes: apply S-box to each byte of state
void SubBytes(u8 state[4][4]) {
  #pragma hls_unroll yes
  for (int i = 0; i < 4; ++i) {
    #pragma hls_unroll yes
    for (int j = 0; j < 4; ++j) {
      state[j][i] = sbox_lookup(state[j][i]);
    }
  }
}

// ShiftRows: cyclically shift rows of state
void ShiftRows(u8 state[4][4]) {
  u8 temp;

  // Row 1: shift left by 1
  temp        = state[0][1];
  state[0][1] = state[1][1];
  state[1][1] = state[2][1];
  state[2][1] = state[3][1];
  state[3][1] = temp;

  // Row 2: shift left by 2
  temp        = state[0][2];
  state[0][2] = state[2][2];
  state[2][2] = temp;
  temp        = state[1][2];
  state[1][2] = state[3][2];
  state[3][2] = temp;

  // Row 3: shift left by 3
  temp        = state[0][3];
  state[0][3] = state[3][3];
  state[3][3] = state[2][3];
  state[2][3] = state[1][3];
  state[1][3] = temp;
}

// MixColumns: mix each column of state
void MixColumns(u8 state[4][4]) {
  #pragma hls_unroll yes
  for (int i = 0; i < 4; ++i) {
    u8 t   = state[i][0];
    u8 Tmp = state[i][0] ^ state[i][1] ^ state[i][2] ^ state[i][3];

    u8 Tm0 = state[i][0] ^ state[i][1];
    Tm0 = xtime(Tm0);
    state[i][0] = state[i][0] ^ (Tm0 ^ Tmp);

    u8 Tm1 = state[i][1] ^ state[i][2];
    Tm1 = xtime(Tm1);
    state[i][1] = state[i][1] ^ (Tm1 ^ Tmp);

    u8 Tm2 = state[i][2] ^ state[i][3];
    Tm2 = xtime(Tm2);
    state[i][2] = state[i][2] ^ (Tm2 ^ Tmp);

    u8 Tm3 = state[i][3] ^ t;
    Tm3 = xtime(Tm3);
    state[i][3] = state[i][3] ^ (Tm3 ^ Tmp);
  }
}

// Cipher: AES-128 encryption of a single 16-byte block
void Cipher(u8 state[4][4], const u8 RoundKey[AES_keyExpSize]) {
  AddRoundKey(0, state, RoundKey);

  #pragma hls_unroll yes
  for (int round = 1; round <= Nr; ++round) {
    SubBytes(state);
    ShiftRows(state);
    if (round != Nr) {
      MixColumns(state);
    }
    AddRoundKey(round, state, RoundKey);
  }
}

// Top-level XLS proc: AES-128 ECB Encrypt
class AesEcb128Encrypt {
 public:
  __xls_channel<AesBlock, __xls_channel_dir_In> key_in;
  __xls_channel<AesBlock, __xls_channel_dir_In> plaintext_in;
  __xls_channel<AesBlock, __xls_channel_dir_Out> ciphertext_out;

  #pragma hls_top
  void Run() {
    AesBlock key_block = key_in.read();
    AesBlock pt_block = plaintext_in.read();

    // Expand key
    u8 RoundKey[AES_keyExpSize];
    KeyExpansion(RoundKey, key_block.data);

    // Copy plaintext into state array (column-major order)
    u8 state[4][4];
    #pragma hls_unroll yes
    for (int i = 0; i < 4; ++i) {
      #pragma hls_unroll yes
      for (int j = 0; j < 4; ++j) {
        state[i][j] = pt_block.data[i * 4 + j];
      }
    }

    // Encrypt
    Cipher(state, RoundKey);

    // Copy state back to output block
    AesBlock ct_block;
    #pragma hls_unroll yes
    for (int i = 0; i < 4; ++i) {
      #pragma hls_unroll yes
      for (int j = 0; j < 4; ++j) {
        ct_block.data[i * 4 + j] = state[i][j];
      }
    }

    ciphertext_out.write(ct_block);
  }
};
