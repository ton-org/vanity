#define F1(x,y,z)   (bitselect(z,y,x))
#define F0(x,y,z)   (bitselect (x, y, ((x) ^ (z))))
#define shr32(x,n) ((x) >> (n))
#define rotl32(a,n) rotate ((a), (n))

#define S0(x) (rotl32 ((x), 25u) ^ rotl32 ((x), 14u) ^ shr32 ((x),  3u))
#define S1(x) (rotl32 ((x), 15u) ^ rotl32 ((x), 13u) ^ shr32 ((x), 10u))
#define S2(x) (rotl32 ((x), 30u) ^ rotl32 ((x), 19u) ^ rotl32 ((x), 10u))
#define S3(x) (rotl32 ((x), 26u) ^ rotl32 ((x), 21u) ^ rotl32 ((x),  7u))

#define SWAP(val) (rotate(((val) & 0x00FF00FF), 24U) | rotate(((val) & 0xFF00FF00), 8U));

#define SHA256C00 0x428a2f98u
#define SHA256C01 0x71374491u
#define SHA256C02 0xb5c0fbcfu
#define SHA256C03 0xe9b5dba5u
#define SHA256C04 0x3956c25bu
#define SHA256C05 0x59f111f1u
#define SHA256C06 0x923f82a4u
#define SHA256C07 0xab1c5ed5u
#define SHA256C08 0xd807aa98u
#define SHA256C09 0x12835b01u
#define SHA256C0a 0x243185beu
#define SHA256C0b 0x550c7dc3u
#define SHA256C0c 0x72be5d74u
#define SHA256C0d 0x80deb1feu
#define SHA256C0e 0x9bdc06a7u
#define SHA256C0f 0xc19bf174u
#define SHA256C10 0xe49b69c1u
#define SHA256C11 0xefbe4786u
#define SHA256C12 0x0fc19dc6u
#define SHA256C13 0x240ca1ccu
#define SHA256C14 0x2de92c6fu
#define SHA256C15 0x4a7484aau
#define SHA256C16 0x5cb0a9dcu
#define SHA256C17 0x76f988dau
#define SHA256C18 0x983e5152u
#define SHA256C19 0xa831c66du
#define SHA256C1a 0xb00327c8u
#define SHA256C1b 0xbf597fc7u
#define SHA256C1c 0xc6e00bf3u
#define SHA256C1d 0xd5a79147u
#define SHA256C1e 0x06ca6351u
#define SHA256C1f 0x14292967u
#define SHA256C20 0x27b70a85u
#define SHA256C21 0x2e1b2138u
#define SHA256C22 0x4d2c6dfcu
#define SHA256C23 0x53380d13u
#define SHA256C24 0x650a7354u
#define SHA256C25 0x766a0abbu
#define SHA256C26 0x81c2c92eu
#define SHA256C27 0x92722c85u
#define SHA256C28 0xa2bfe8a1u
#define SHA256C29 0xa81a664bu
#define SHA256C2a 0xc24b8b70u
#define SHA256C2b 0xc76c51a3u
#define SHA256C2c 0xd192e819u
#define SHA256C2d 0xd6990624u
#define SHA256C2e 0xf40e3585u
#define SHA256C2f 0x106aa070u
#define SHA256C30 0x19a4c116u
#define SHA256C31 0x1e376c08u
#define SHA256C32 0x2748774cu
#define SHA256C33 0x34b0bcb5u
#define SHA256C34 0x391c0cb3u
#define SHA256C35 0x4ed8aa4au
#define SHA256C36 0x5b9cca4fu
#define SHA256C37 0x682e6ff3u
#define SHA256C38 0x748f82eeu
#define SHA256C39 0x78a5636fu
#define SHA256C3a 0x84c87814u
#define SHA256C3b 0x8cc70208u
#define SHA256C3c 0x90befffau
#define SHA256C3d 0xa4506cebu
#define SHA256C3e 0xbef9a3f7u
#define SHA256C3f 0xc67178f2u

__constant uint k_sha256[64] =
{
  SHA256C00, SHA256C01, SHA256C02, SHA256C03,
  SHA256C04, SHA256C05, SHA256C06, SHA256C07,
  SHA256C08, SHA256C09, SHA256C0a, SHA256C0b,
  SHA256C0c, SHA256C0d, SHA256C0e, SHA256C0f,
  SHA256C10, SHA256C11, SHA256C12, SHA256C13,
  SHA256C14, SHA256C15, SHA256C16, SHA256C17,
  SHA256C18, SHA256C19, SHA256C1a, SHA256C1b,
  SHA256C1c, SHA256C1d, SHA256C1e, SHA256C1f,
  SHA256C20, SHA256C21, SHA256C22, SHA256C23,
  SHA256C24, SHA256C25, SHA256C26, SHA256C27,
  SHA256C28, SHA256C29, SHA256C2a, SHA256C2b,
  SHA256C2c, SHA256C2d, SHA256C2e, SHA256C2f,
  SHA256C30, SHA256C31, SHA256C32, SHA256C33,
  SHA256C34, SHA256C35, SHA256C36, SHA256C37,
  SHA256C38, SHA256C39, SHA256C3a, SHA256C3b,
  SHA256C3c, SHA256C3d, SHA256C3e, SHA256C3f,
};

#define SHA256_STEP(F0a,F1a,a,b,c,d,e,f,g,h,x,K)  \
{                                                 \
  h += K;                                         \
  h += x;                                         \
  h += S3 (e);                                    \
  h += F1a (e,f,g);                               \
  d += h;                                         \
  h += S2 (a);                                    \
  h += F0a (a,b,c);                               \
}

#define SHA256_EXPAND(x,y,z,w) (S1 (x) + y + S0 (z) + w)

static void sha256_process2 (const unsigned int *W, unsigned int *digest)
{
  unsigned int a = digest[0];
  unsigned int b = digest[1];
  unsigned int c = digest[2];
  unsigned int d = digest[3];
  unsigned int e = digest[4];
  unsigned int f = digest[5];
  unsigned int g = digest[6];
  unsigned int h = digest[7];

  unsigned int w0_t = W[0];
  unsigned int w1_t = W[1];
  unsigned int w2_t = W[2];
  unsigned int w3_t = W[3];
  unsigned int w4_t = W[4];
  unsigned int w5_t = W[5];
  unsigned int w6_t = W[6];
  unsigned int w7_t = W[7];
  unsigned int w8_t = W[8];
  unsigned int w9_t = W[9];
  unsigned int wa_t = W[10];
  unsigned int wb_t = W[11];
  unsigned int wc_t = W[12];
  unsigned int wd_t = W[13];
  unsigned int we_t = W[14];
  unsigned int wf_t = W[15];

  #define ROUND_EXPAND()                           \
  {                                                \
    w0_t = SHA256_EXPAND (we_t, w9_t, w1_t, w0_t); \
    w1_t = SHA256_EXPAND (wf_t, wa_t, w2_t, w1_t); \
    w2_t = SHA256_EXPAND (w0_t, wb_t, w3_t, w2_t); \
    w3_t = SHA256_EXPAND (w1_t, wc_t, w4_t, w3_t); \
    w4_t = SHA256_EXPAND (w2_t, wd_t, w5_t, w4_t); \
    w5_t = SHA256_EXPAND (w3_t, we_t, w6_t, w5_t); \
    w6_t = SHA256_EXPAND (w4_t, wf_t, w7_t, w6_t); \
    w7_t = SHA256_EXPAND (w5_t, w0_t, w8_t, w7_t); \
    w8_t = SHA256_EXPAND (w6_t, w1_t, w9_t, w8_t); \
    w9_t = SHA256_EXPAND (w7_t, w2_t, wa_t, w9_t); \
    wa_t = SHA256_EXPAND (w8_t, w3_t, wb_t, wa_t); \
    wb_t = SHA256_EXPAND (w9_t, w4_t, wc_t, wb_t); \
    wc_t = SHA256_EXPAND (wa_t, w5_t, wd_t, wc_t); \
    wd_t = SHA256_EXPAND (wb_t, w6_t, we_t, wd_t); \
    we_t = SHA256_EXPAND (wc_t, w7_t, wf_t, we_t); \
    wf_t = SHA256_EXPAND (wd_t, w8_t, w0_t, wf_t); \
  }

  #define ROUND_STEP(i)                                                                   \
  {                                                                                       \
    SHA256_STEP (F0, F1, a, b, c, d, e, f, g, h, w0_t, k_sha256[i +  0]);                 \
    SHA256_STEP (F0, F1, h, a, b, c, d, e, f, g, w1_t, k_sha256[i +  1]);                 \
    SHA256_STEP (F0, F1, g, h, a, b, c, d, e, f, w2_t, k_sha256[i +  2]);                 \
    SHA256_STEP (F0, F1, f, g, h, a, b, c, d, e, w3_t, k_sha256[i +  3]);                 \
    SHA256_STEP (F0, F1, e, f, g, h, a, b, c, d, w4_t, k_sha256[i +  4]);                 \
    SHA256_STEP (F0, F1, d, e, f, g, h, a, b, c, w5_t, k_sha256[i +  5]);                 \
    SHA256_STEP (F0, F1, c, d, e, f, g, h, a, b, w6_t, k_sha256[i +  6]);                 \
    SHA256_STEP (F0, F1, b, c, d, e, f, g, h, a, w7_t, k_sha256[i +  7]);                 \
    SHA256_STEP (F0, F1, a, b, c, d, e, f, g, h, w8_t, k_sha256[i +  8]);                 \
    SHA256_STEP (F0, F1, h, a, b, c, d, e, f, g, w9_t, k_sha256[i +  9]);                 \
    SHA256_STEP (F0, F1, g, h, a, b, c, d, e, f, wa_t, k_sha256[i + 10]);                 \
    SHA256_STEP (F0, F1, f, g, h, a, b, c, d, e, wb_t, k_sha256[i + 11]);                 \
    SHA256_STEP (F0, F1, e, f, g, h, a, b, c, d, wc_t, k_sha256[i + 12]);                 \
    SHA256_STEP (F0, F1, d, e, f, g, h, a, b, c, wd_t, k_sha256[i + 13]);                 \
    SHA256_STEP (F0, F1, c, d, e, f, g, h, a, b, we_t, k_sha256[i + 14]);                 \
    SHA256_STEP (F0, F1, b, c, d, e, f, g, h, a, wf_t, k_sha256[i + 15]);                 \
  }

  ROUND_STEP (0);

  ROUND_EXPAND();
  ROUND_STEP(16);

  ROUND_EXPAND();
  ROUND_STEP(32);

  ROUND_EXPAND();
  ROUND_STEP(48);

  digest[0] += a;
  digest[1] += b;
  digest[2] += c;
  digest[3] += d;
  digest[4] += e;
  digest[5] += f;
  digest[6] += g;
  digest[7] += h;
}

#undef F0
#undef F1
#undef S0
#undef S1
#undef S2
#undef S3

#undef shr32
#undef rotl32
// first 64 bytes of code cell (constant w.r.t salt), injected from host
__constant uchar CODE_PREFIX[64] = { <<CODE_PREFIX_BYTES>> };
__constant uint CODE_STATE_BASE[8] = { <<CODE_STATE_BASE>> };

// configuration injected from host
#define FLAGS_HI <<FLAGS_HI>>
#define FLAGS_LO <<FLAGS_LO>>
#define FREE_HASH_MASK <<FREE_HASH_MASK>>
#define FREE_HASH_VAL  <<FREE_HASH_VAL>>
#define N_STATEINIT_VARIANTS <<N_STATEINIT_VARIANTS>>
#define STATEINIT_PREFIX_MAX_LEN <<STATEINIT_PREFIX_MAX_LEN>>
#define HAS_CRC_CONSTRAINT <<HAS_CRC_CONSTRAINT>>
#define N_ACTIVE <<N_ACTIVE>>
#define N_ACTIVE_NOCRC <<N_ACTIVE_NOCRC>>
#define N_CASE_INSENSITIVE <<N_CASE_INSENSITIVE>>

// Byte-level masks for prefix matching (36 bytes)
__constant uchar PREFIX_MASK[36] = { <<PREFIX_MASK>> };
__constant uchar PREFIX_VAL[36]  = { <<PREFIX_VAL>> };

#if N_CASE_INSENSITIVE > 0
__constant ushort CASE_BITPOS[N_CASE_INSENSITIVE] = { <<CASE_BITPOS>> };
__constant uchar  CASE_ALT0[N_CASE_INSENSITIVE] = { <<CASE_ALT0>> };
__constant uchar  CASE_ALT1[N_CASE_INSENSITIVE] = { <<CASE_ALT1>> };
#endif

// CRC16 lookup table injected from host
__constant ushort CRC16_TABLE[256] = { <<CRC16_TABLE>> };

__constant uchar STATEINIT_PREFIX_LENS[N_STATEINIT_VARIANTS] = { <<STATEINIT_PREFIX_LENS>> };
__constant uchar STATEINIT_PREFIX_VARIANTS[N_STATEINIT_VARIANTS][STATEINIT_PREFIX_MAX_LEN] = {
    <<STATEINIT_PREFIX_MATRIX>>
};

#if N_ACTIVE > 0
__constant uchar PREFIX_POS[N_ACTIVE] = { <<PREFIX_POS>> };
#endif
#if N_ACTIVE_NOCRC > 0
__constant uchar PREFIX_POS_NOCRC[N_ACTIVE_NOCRC] = { <<PREFIX_POS_NOCRC>> };
#endif

// prepacked prefix contribution to message block words
__constant uint PREFIX_W[N_STATEINIT_VARIANTS][16] = {
    <<PREFIX_W_MATRIX>>
};

__constant uint SHA256_IV[8] = {
    0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
    0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u
};

// Fast CRC16-CCITT using lookup table (poly 0x1021, init 0x0000)
inline ushort gen_crc16_fast(const uchar *data, int size)
{
    ushort crc = 0;
    for (int i = 0; i < size; i++) {
        crc = (ushort)((crc << 8) ^ CRC16_TABLE[((crc >> 8) ^ data[i]) & 0xff]);
    }
    return crc;
}

__kernel void hash_main(
    int iterations,
    uint salt0,
    uint salt1,
    uint salt2,
    uint salt3,
    volatile __global uint *found_counter,
    __global unsigned int * restrict res
)
{
    uint idx = get_global_id(0);

    uint W[16];
    uint code_hash_state[8];
    uint main_hash[8];

    for (int iter = 0; iter < iterations; iter++) {
        // derive 128-bit salt from base salt and (iter, idx)
        uint s0 = salt0 ^ (uint)iter;
        uint s1 = salt1 ^ (uint)idx;
        uint s2 = salt2;
        uint s3 = salt3;

        W[0] = SWAP(s0);
        W[1] = SWAP(s1);
        W[2] = SWAP(s2);
        W[3] = SWAP(s3);
        W[4]  = 0x80000000u;
        W[5]  = 0u;
        W[6]  = 0u;
        W[7]  = 0u;
        W[8]  = 0u;
        W[9]  = 0u;
        W[10] = 0u;
        W[11] = 0u;
        W[12] = 0u;
        W[13] = 0u;
        W[14] = 0u;
        W[15] = 640u; // total bits of code cell (80 bytes)

        #pragma unroll
        for (int i = 0; i < 8; i++) {
            code_hash_state[i] = CODE_STATE_BASE[i];
        }
        sha256_process2(W, code_hash_state);
        #pragma unroll
        for (int i = 0; i < 8; i++) {
            code_hash_state[i] = SWAP(code_hash_state[i]);
        }

        uchar *ch = (uchar *)code_hash_state;

        #if N_STATEINIT_VARIANTS == 5
        #pragma unroll
        #endif
        for (int v = 0; v < N_STATEINIT_VARIANTS; v++) {
            uchar prefix_len = STATEINIT_PREFIX_LENS[v];
            const int main_len = (int)prefix_len + 32; // bytes, always < 56 here

            #pragma unroll
            for (int i = 0; i < 16; i++) {
                W[i] = PREFIX_W[v][i];
            }

            // insert code hash bytes into pre-packed prefix words
            for (int j = 0; j < 32; j++) {
                int idx_b = (int)prefix_len + j;
                int w = idx_b >> 2;
                int shift = 24 - ((idx_b & 3) * 8);
                W[w] |= (uint)ch[j] << shift;
            }

            // padding bit
            int pad_w = main_len >> 2;
            int pad_shift = 24 - ((main_len & 3) * 8);
            W[pad_w] |= (uint)0x80 << pad_shift;
            // length in bits
            W[15] = (uint)main_len * 8u;

            #pragma unroll
            for (int i = 0; i < 8; i++) {
                main_hash[i] = SHA256_IV[i];
            }
            sha256_process2(W, main_hash);
            #pragma unroll
            for (int i = 0; i < 8; i++) {
                main_hash[i] = SWAP(main_hash[i]);
            }

            // --- OPTIMIZATION START ---
            uchar *mhb = (uchar *)main_hash;
            int ok = 1;

            // rewrite first hash byte with FREE_HASH_MASK/FREE_HASH_VAL
            uchar hash0 = (uchar)((mhb[0] & (~FREE_HASH_MASK)) | (FREE_HASH_VAL & FREE_HASH_MASK));

            // early check on non-CRC constrained bytes
#if N_ACTIVE_NOCRC > 0
            if (ok) {
                #pragma unroll
                for (int j = 0; j < N_ACTIVE_NOCRC; j++) {
                    int i = PREFIX_POS_NOCRC[j];
                    uchar val = 0;
                    if (i == 2) {
                        val = hash0;
                    } else if (i >= 0 && i < 36) {
                        val = (i >= 3 && i < 34) ? mhb[i - 2] : (uchar)0;
                    }
                    if ((val & PREFIX_MASK[i]) != PREFIX_VAL[i]) {
                        ok = 0;
                        break;
                    }
                }
            }
#endif

            if (ok) {
                uchar repr[36];
                repr[0] = (uchar)FLAGS_HI;
                repr[1] = (uchar)FLAGS_LO;
                repr[2] = hash0;

                #pragma unroll
                for (int k = 1; k < 32; k++) {
                    repr[2 + k] = mhb[k];
                }

                repr[34] = 0;
                repr[35] = 0;

                if (HAS_CRC_CONSTRAINT) {
                    ushort crc = gen_crc16_fast((uchar *)repr, 34);
                    repr[34] = (uchar)(crc >> 8);
                    repr[35] = (uchar)(crc & 0xffu);

#if N_ACTIVE > 0
                    #pragma unroll
                    for (int j = 0; j < N_ACTIVE; j++) {
                        int i = PREFIX_POS[j];
                        if ((repr[i] & PREFIX_MASK[i]) != PREFIX_VAL[i]) {
                            ok = 0;
                            break;
                        }
                    }
#endif
                }

#if N_CASE_INSENSITIVE > 0
                if (ok) {
                    #pragma unroll
                    for (int j = 0; j < N_CASE_INSENSITIVE; j++) {
                        ushort bit = CASE_BITPOS[j];
                        int byte = (int)(bit >> 3);
                        int bit_in_byte = 7 - (int)(bit & 7);
                        ushort comb = ((ushort)repr[byte] << 8) | (ushort)((byte + 1 < 36) ? repr[byte + 1] : 0);
                        uchar val6 = (uchar)((comb >> (bit_in_byte + 3)) & 0x3fu);
                        if ((val6 != CASE_ALT0[j]) && (val6 != CASE_ALT1[j])) {
                            ok = 0;
                            break;
                        }
                    }
                }
#endif

                if (ok) {
                    uint slot = atomic_inc(found_counter);
                    if (slot < 1024u) {
                        res[slot * 3]     = (uint)iter;
                        res[slot * 3 + 1] = idx;
                        res[slot * 3 + 2] = (uint)v;
                    }
                }
            }
            // --- OPTIMIZATION END ---
        }
    }
}
