// --- SHA256 Definitions and Optimizations ---

#define F1(x,y,z)   (bitselect(z,y,x))
#define F0(x,y,z)   (bitselect (x, y, ((x) ^ (z))))
#define shr32(x,n) ((x) >> (n))
#define rotl32(a,n) rotate ((a), (n))

#define S0(x) (rotl32 ((x), 25u) ^ rotl32 ((x), 14u) ^ shr32 ((x),  3u))
#define S1(x) (rotl32 ((x), 15u) ^ rotl32 ((x), 13u) ^ shr32 ((x), 10u))
#define S2(x) (rotl32 ((x), 30u) ^ rotl32 ((x), 19u) ^ rotl32 ((x), 10u))
#define S3(x) (rotl32 ((x), 26u) ^ rotl32 ((x), 21u) ^ rotl32 ((x),  7u))

// Optimization: Efficient Byte Swapping using vector shuffling.
#define SWAP(val) (as_uint(as_uchar4(val).wzyx))

// Macro to extract byte k from a BE uint array (SHA256 natural word order).
#define GET_BYTE_BE_ARRAY(arr, k) ((uchar)((arr[(k) >> 2] >> (24 - (((k) & 3) << 3))) & 0xFF))

// SHA256 Constants (Used as immediate values)
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

#define SHA256_EXPAND(x,y,z,w) (S1 (x) + y + S0 (z) + w)

// Optimization: ILP optimized SHA256 STEP (T1/T2 formulation). Takes combined K+W (KW).
#define SHA256_STEP_OPT(F0a,F1a,a,b,c,d,e,f,g,h,KW) \
{                                                   \
  uint T1 = h + S3(e) + F1a(e,f,g) + KW;            \
  uint T2 = S2(a) + F0a(a,b,c);                     \
  d += T1;                                          \
  h = T1 + T2;                                      \
}

// Rounds 0-15: Combine K+W using immediate constants.
#define ROUND_0_15_IMM(a, b, c, d, e, f, g, h, w, K_IMM) \
{ \
    SHA256_STEP_OPT(F0, F1, a, b, c, d, e, f, g, h, w + K_IMM); \
}

// Rounds 16-63: Interleaved expansion and compression using immediate constants.
// W_i_16 is updated in place (register reuse).
#define ROUND_16_63_IMM(a, b, c, d, e, f, g, h, W_i_16, W_i_15, W_i_7, W_i_2, K_IMM) \
{ \
    W_i_16 = SHA256_EXPAND(W_i_2, W_i_7, W_i_15, W_i_16); \
    SHA256_STEP_OPT(F0, F1, a, b, c, d, e, f, g, h, W_i_16 + K_IMM); \
}

// Maximally optimized SHA256 process function: Fully Unrolled, Interleaved, ILP Optimized, Immediate Constants.
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

  // Load W into private registers
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

  // --- Fully Unrolled Rounds ---

  // Rounds 0-15
  ROUND_0_15_IMM(a, b, c, d, e, f, g, h, w0_t, SHA256C00);
  ROUND_0_15_IMM(h, a, b, c, d, e, f, g, w1_t, SHA256C01);
  ROUND_0_15_IMM(g, h, a, b, c, d, e, f, w2_t, SHA256C02);
  ROUND_0_15_IMM(f, g, h, a, b, c, d, e, w3_t, SHA256C03);
  ROUND_0_15_IMM(e, f, g, h, a, b, c, d, w4_t, SHA256C04);
  ROUND_0_15_IMM(d, e, f, g, h, a, b, c, w5_t, SHA256C05);
  ROUND_0_15_IMM(c, d, e, f, g, h, a, b, w6_t, SHA256C06);
  ROUND_0_15_IMM(b, c, d, e, f, g, h, a, w7_t, SHA256C07);
  ROUND_0_15_IMM(a, b, c, d, e, f, g, h, w8_t, SHA256C08);
  ROUND_0_15_IMM(h, a, b, c, d, e, f, g, w9_t, SHA256C09);
  ROUND_0_15_IMM(g, h, a, b, c, d, e, f, wa_t, SHA256C0a);
  ROUND_0_15_IMM(f, g, h, a, b, c, d, e, wb_t, SHA256C0b);
  ROUND_0_15_IMM(e, f, g, h, a, b, c, d, wc_t, SHA256C0c);
  ROUND_0_15_IMM(d, e, f, g, h, a, b, c, wd_t, SHA256C0d);
  ROUND_0_15_IMM(c, d, e, f, g, h, a, b, we_t, SHA256C0e);
  ROUND_0_15_IMM(b, c, d, e, f, g, h, a, wf_t, SHA256C0f);

  // Rounds 16-31 (Interleaved)
  ROUND_16_63_IMM(a, b, c, d, e, f, g, h, w0_t, w1_t, w9_t, we_t, SHA256C10);
  ROUND_16_63_IMM(h, a, b, c, d, e, f, g, w1_t, w2_t, wa_t, wf_t, SHA256C11);
  ROUND_16_63_IMM(g, h, a, b, c, d, e, f, w2_t, w3_t, wb_t, w0_t, SHA256C12);
  ROUND_16_63_IMM(f, g, h, a, b, c, d, e, w3_t, w4_t, wc_t, w1_t, SHA256C13);
  ROUND_16_63_IMM(e, f, g, h, a, b, c, d, w4_t, w5_t, wd_t, w2_t, SHA256C14);
  ROUND_16_63_IMM(d, e, f, g, h, a, b, c, w5_t, w6_t, we_t, w3_t, SHA256C15);
  ROUND_16_63_IMM(c, d, e, f, g, h, a, b, w6_t, w7_t, wf_t, w4_t, SHA256C16);
  ROUND_16_63_IMM(b, c, d, e, f, g, h, a, w7_t, w8_t, w0_t, w5_t, SHA256C17);
  ROUND_16_63_IMM(a, b, c, d, e, f, g, h, w8_t, w9_t, w1_t, w6_t, SHA256C18);
  ROUND_16_63_IMM(h, a, b, c, d, e, f, g, w9_t, wa_t, w2_t, w7_t, SHA256C19);
  ROUND_16_63_IMM(g, h, a, b, c, d, e, f, wa_t, wb_t, w3_t, w8_t, SHA256C1a);
  ROUND_16_63_IMM(f, g, h, a, b, c, d, e, wb_t, wc_t, w4_t, w9_t, SHA256C1b);
  ROUND_16_63_IMM(e, f, g, h, a, b, c, d, wc_t, wd_t, w5_t, wa_t, SHA256C1c);
  ROUND_16_63_IMM(d, e, f, g, h, a, b, c, wd_t, we_t, w6_t, wb_t, SHA256C1d);
  ROUND_16_63_IMM(c, d, e, f, g, h, a, b, we_t, wf_t, w7_t, wc_t, SHA256C1e);
  ROUND_16_63_IMM(b, c, d, e, f, g, h, a, wf_t, w0_t, w8_t, wd_t, SHA256C1f);

  // Rounds 32-47 (Interleaved)
  ROUND_16_63_IMM(a, b, c, d, e, f, g, h, w0_t, w1_t, w9_t, we_t, SHA256C20);
  ROUND_16_63_IMM(h, a, b, c, d, e, f, g, w1_t, w2_t, wa_t, wf_t, SHA256C21);
  ROUND_16_63_IMM(g, h, a, b, c, d, e, f, w2_t, w3_t, wb_t, w0_t, SHA256C22);
  ROUND_16_63_IMM(f, g, h, a, b, c, d, e, w3_t, w4_t, wc_t, w1_t, SHA256C23);
  ROUND_16_63_IMM(e, f, g, h, a, b, c, d, w4_t, w5_t, wd_t, w2_t, SHA256C24);
  ROUND_16_63_IMM(d, e, f, g, h, a, b, c, w5_t, w6_t, we_t, w3_t, SHA256C25);
  ROUND_16_63_IMM(c, d, e, f, g, h, a, b, w6_t, w7_t, wf_t, w4_t, SHA256C26);
  ROUND_16_63_IMM(b, c, d, e, f, g, h, a, w7_t, w8_t, w0_t, w5_t, SHA256C27);
  ROUND_16_63_IMM(a, b, c, d, e, f, g, h, w8_t, w9_t, w1_t, w6_t, SHA256C28);
  ROUND_16_63_IMM(h, a, b, c, d, e, f, g, w9_t, wa_t, w2_t, w7_t, SHA256C29);
  ROUND_16_63_IMM(g, h, a, b, c, d, e, f, wa_t, wb_t, w3_t, w8_t, SHA256C2a);
  ROUND_16_63_IMM(f, g, h, a, b, c, d, e, wb_t, wc_t, w4_t, w9_t, SHA256C2b);
  ROUND_16_63_IMM(e, f, g, h, a, b, c, d, wc_t, wd_t, w5_t, wa_t, SHA256C2c);
  ROUND_16_63_IMM(d, e, f, g, h, a, b, c, wd_t, we_t, w6_t, wb_t, SHA256C2d);
  ROUND_16_63_IMM(c, d, e, f, g, h, a, b, we_t, wf_t, w7_t, wc_t, SHA256C2e);
  ROUND_16_63_IMM(b, c, d, e, f, g, h, a, wf_t, w0_t, w8_t, wd_t, SHA256C2f);

  // Rounds 48-63 (Interleaved)
  ROUND_16_63_IMM(a, b, c, d, e, f, g, h, w0_t, w1_t, w9_t, we_t, SHA256C30);
  ROUND_16_63_IMM(h, a, b, c, d, e, f, g, w1_t, w2_t, wa_t, wf_t, SHA256C31);
  ROUND_16_63_IMM(g, h, a, b, c, d, e, f, w2_t, w3_t, wb_t, w0_t, SHA256C32);
  ROUND_16_63_IMM(f, g, h, a, b, c, d, e, w3_t, w4_t, wc_t, w1_t, SHA256C33);
  ROUND_16_63_IMM(e, f, g, h, a, b, c, d, w4_t, w5_t, wd_t, w2_t, SHA256C34);
  ROUND_16_63_IMM(d, e, f, g, h, a, b, c, w5_t, w6_t, we_t, w3_t, SHA256C35);
  ROUND_16_63_IMM(c, d, e, f, g, h, a, b, w6_t, w7_t, wf_t, w4_t, SHA256C36);
  ROUND_16_63_IMM(b, c, d, e, f, g, h, a, w7_t, w8_t, w0_t, w5_t, SHA256C37);
  ROUND_16_63_IMM(a, b, c, d, e, f, g, h, w8_t, w9_t, w1_t, w6_t, SHA256C38);
  ROUND_16_63_IMM(h, a, b, c, d, e, f, g, w9_t, wa_t, w2_t, w7_t, SHA256C39);
  ROUND_16_63_IMM(g, h, a, b, c, d, e, f, wa_t, wb_t, w3_t, w8_t, SHA256C3a);
  ROUND_16_63_IMM(f, g, h, a, b, c, d, e, wb_t, wc_t, w4_t, w9_t, SHA256C3b);
  ROUND_16_63_IMM(e, f, g, h, a, b, c, d, wc_t, wd_t, w5_t, wa_t, SHA256C3c);
  ROUND_16_63_IMM(d, e, f, g, h, a, b, c, wd_t, we_t, w6_t, wb_t, SHA256C3d);
  ROUND_16_63_IMM(c, d, e, f, g, h, a, b, we_t, wf_t, w7_t, wc_t, SHA256C3e);
  ROUND_16_63_IMM(b, c, d, e, f, g, h, a, wf_t, w0_t, w8_t, wd_t, SHA256C3f);

  #undef ROUND_0_15_IMM
  #undef ROUND_16_63_IMM

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
#undef SHA256_STEP_OPT

// --- Configuration injected from host (Placeholders) ---

// first 64 bytes of code cell (constant w.r.t salt), injected from host
__constant uchar CODE_PREFIX[64] = { <<CODE_PREFIX_BYTES>> };
__constant uint CODE_STATE_BASE[8] = { <<CODE_STATE_BASE>> };

// configuration injected from host
#define FLAGS_HI <<FLAGS_HI>>
#define FLAGS_LO <<FLAGS_LO>>
#define FREE_HASH_MASK <<FREE_HASH_MASK>>
#define FREE_HASH_VAL  <<FREE_HASH_VAL>>
#define NEED_CRC <<NEED_CRC>>
#define HASH0_COUNT <<HASH0_COUNT>>
#define N_STATEINIT_VARIANTS <<N_STATEINIT_VARIANTS>>
#define STATEINIT_PREFIX_MAX_LEN <<STATEINIT_PREFIX_MAX_LEN>>
#define N_ACTIVE <<N_ACTIVE>>
#define N_ACTIVE_NOCRC <<N_ACTIVE_NOCRC>>
#define N_CASE_CONST <<N_CASE_CONST>>
#define N_CASE_VAR <<N_CASE_VAR>>

// Byte-level masks for prefix matching (36 bytes)
__constant uchar PREFIX_MASK[36] = { <<PREFIX_MASK>> };
__constant uchar PREFIX_VAL[36]  = { <<PREFIX_VAL>> };

// Allowed values for the first hash byte (repr[2]) given fixedPrefixLength=8
// and any forced bits coming from the start pattern.
__constant uchar HASH0_VALUES[256] = { <<HASH0_VALUES>> };

#if N_CASE_CONST > 0
__constant ushort CASE_CONST_BITPOS[N_CASE_CONST] = { <<CASE_CONST_BITPOS>> };
__constant uchar  CASE_CONST_ALT0[N_CASE_CONST] = { <<CASE_CONST_ALT0>> };
__constant uchar  CASE_CONST_ALT1[N_CASE_CONST] = { <<CASE_CONST_ALT1>> };
#endif

#if N_CASE_VAR > 0
__constant ushort CASE_VAR_BITPOS[N_CASE_VAR] = { <<CASE_VAR_BITPOS>> };
__constant uchar  CASE_VAR_ALT0[N_CASE_VAR] = { <<CASE_VAR_ALT0>> };
__constant uchar  CASE_VAR_ALT1[N_CASE_VAR] = { <<CASE_VAR_ALT1>> };
#endif

// CRC16 lookup table injected from host
__constant ushort CRC16_TABLE[256] = { <<CRC16_TABLE>> };
// CRC16 deltas for 34-byte message where only byte index 2 changes.
__constant ushort CRC16_DELTA_POS2[256] = { <<CRC16_DELTA_POS2>> };

__constant uchar STATEINIT_PREFIX_LENS[N_STATEINIT_VARIANTS] = { <<STATEINIT_PREFIX_LENS>> };
// STATEINIT_PREFIX_VARIANTS is unused in the optimized kernel logic.

#if N_ACTIVE > 0
__constant uchar PREFIX_POS[N_ACTIVE] = { <<PREFIX_POS>> };
#endif
#if N_ACTIVE_NOCRC > 0
__constant uchar PREFIX_POS_NOCRC[N_ACTIVE_NOCRC] = { <<PREFIX_POS_NOCRC>> };
#endif

// prepacked prefix contribution to message block words (Assumed zero-padded by host)
__constant uint PREFIX_W[N_STATEINIT_VARIANTS][16] = {
    <<PREFIX_W_MATRIX>>
};

__constant uint SHA256_IV[8] = {
    0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
    0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u
};

inline ushort crc16_update(const ushort crc, const uchar b)
{
    return (ushort)((crc << 8) ^ CRC16_TABLE[((crc >> 8) ^ b) & 0xff]);
}

inline uchar repr_byte(const int i, const uchar hash0, const uint *main_hash, const ushort crc)
{
    if (i == 0) return (uchar)FLAGS_HI;
    if (i == 1) return (uchar)FLAGS_LO;
    if (i == 2) return hash0;
    if (i < 34) return GET_BYTE_BE_ARRAY(main_hash, i - 2);
    if (i == 34) return (uchar)(crc >> 8);
    return (uchar)(crc & 0xffu);
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

    // Allocate private memory (registers)
    uint W[16];
    uint code_hash_state[8];
    uint main_hash[8];

    for (int iter = 0; iter < iterations; iter++) {
        // --- First Hash (Code Hash) ---

        // derive 128-bit salt
        uint s0 = salt0 ^ (uint)iter;
        uint s1 = salt1 ^ (uint)idx;
        uint s2 = salt2;
        uint s3 = salt3;

        // Prepare message block W (BE). Using optimized SWAP.
        W[0] = SWAP(s0);
        W[1] = SWAP(s1);
        W[2] = SWAP(s2);
        W[3] = SWAP(s3);
        W[4]  = 0x80000000u;
        #pragma unroll
        for (int i = 5; i < 15; i++) {
            W[i] = 0u;
        }
        W[15] = 640u; // 80 bytes * 8 bits/byte

        // Calculate code_hash_state
        #pragma unroll
        for (int i = 0; i < 8; i++) {
            code_hash_state[i] = CODE_STATE_BASE[i];
        }
        sha256_process2(W, code_hash_state);
        // code_hash_state is now in Big Endian format.

        // --- Second Hash (Main Hash) and Checks ---

        // Aggressively unroll the variant loop if count is small (e.g. <= 16).
        #if N_STATEINIT_VARIANTS > 0 && N_STATEINIT_VARIANTS <= 16
        #pragma unroll
        #endif
        for (int v = 0; v < N_STATEINIT_VARIANTS; v++) {
            uchar prefix_len = STATEINIT_PREFIX_LENS[v];
            const int main_len = (int)prefix_len + 32;

            // Initialize W (BE) from pre-packed prefix words (BE)
            #pragma unroll
            for (int i = 0; i < 16; i++) {
                W[i] = PREFIX_W[v][i];
            }

            // Optimization: Word-level Message Block Packing (Funnel Shifting).
            // Insert code_hash_state (BE) into W (BE).
            const uint alignment = prefix_len & 3;
            const int start_w = prefix_len >> 2;

            if (alignment == 0) {
                // Aligned insertion
                #pragma unroll
                for (int i = 0; i < 8; i++) {
                    // Use |= assuming PREFIX_W is zero-padded correctly.
                    W[start_w + i] |= code_hash_state[i];
                }
            } else {
                // Unaligned insertion (Right funnel shift for BE data).
                const uint shift_r = alignment << 3; // alignment * 8
                const uint shift_l = 32 - shift_r;

                uint prev = 0;
                #pragma unroll
                for (int i = 0; i < 8; i++) {
                    uint current = code_hash_state[i];
                    // Funnel shift: merge prev (high part/spillover) and current (low part).
                    W[start_w + i] |= (current >> shift_r) | prev;
                    // Calculate spillover for the next word.
                    prev = current << shift_l;
                }
                // Handle the final spillover word. (Safe because main_len < 56).
                W[start_w + 8] |= prev;
            }

            // Add padding bit
            int pad_w = main_len >> 2;
            int pad_shift = 24 - ((main_len & 3) << 3); // Optimized shift calculation
            W[pad_w] |= (uint)0x80 << pad_shift;
            // Add length in bits (BE). Optimized multiplication.
            W[15] = (uint)main_len << 3;

            // Calculate main_hash
            #pragma unroll
            for (int i = 0; i < 8; i++) {
                main_hash[i] = SHA256_IV[i];
            }
            sha256_process2(W, main_hash);

            // --- Constraint Checking ---
            int ok = 1;

            // Early check on non-CRC constrained bytes. This must not depend on
            // the first hash byte, which is swept later via HASH0_VALUES.
#if N_ACTIVE_NOCRC > 0
            if (ok) {
                #pragma unroll
                for (int j = 0; j < N_ACTIVE_NOCRC; j++) {
                    int i = PREFIX_POS_NOCRC[j];
                    // Host guarantees PREFIX_POS_NOCRC contains only bytes 3..33.
                    uchar val = GET_BYTE_BE_ARRAY(main_hash, i - 2);

                    if ((val & PREFIX_MASK[i]) != PREFIX_VAL[i]) {
                        ok = 0;
                        break;
                    }
                }
            }
#endif

            if (!ok) {
                continue;
            }

            // Case-insensitivity constraints that do not depend on hash0 or CRC.
#if N_CASE_CONST > 0
            if (ok) {
                #pragma unroll
                for (int j = 0; j < N_CASE_CONST; j++) {
                    ushort bit = CASE_CONST_BITPOS[j];
                    int byte_idx = (int)(bit >> 3);
                    int bit_in_byte = 7 - (int)(bit & 7);

                    uchar byte0 = repr_byte(byte_idx, (uchar)0, main_hash, (ushort)0);
                    uchar byte1 = (byte_idx + 1 < 36)
                        ? repr_byte(byte_idx + 1, (uchar)0, main_hash, (ushort)0)
                        : 0;

                    ushort comb = ((ushort)byte0 << 8) | (ushort)byte1;
                    uchar val6 = (uchar)((comb >> (bit_in_byte + 3)) & 0x3fu);

                    if ((val6 != CASE_CONST_ALT0[j]) && (val6 != CASE_CONST_ALT1[j])) {
                        ok = 0;
                        break;
                    }
                }
            }
#endif

            if (!ok) {
                continue;
            }

            // Fast path: no CRC needed at all (no constraints on CRC bytes and
            // no case-insensitive digits touching them). Keep legacy behavior:
            // rewrite first hash byte once using FREE_HASH_* and only run CI.
#if NEED_CRC == 0
            {
                uchar H0 = GET_BYTE_BE_ARRAY(main_hash, 0);
                uchar hash0 = (uchar)((H0 & (~FREE_HASH_MASK)) | (FREE_HASH_VAL & FREE_HASH_MASK));
                int ok_local = 1;

                // Case-insensitivity constraints that depend on hash0 (byte 2).
        #if N_CASE_VAR > 0
                if (ok_local) {
                    #pragma unroll
                    for (int j = 0; j < N_CASE_VAR; j++) {
                        ushort bit = CASE_VAR_BITPOS[j];
                        int byte_idx = (int)(bit >> 3);
                        int bit_in_byte = 7 - (int)(bit & 7);

                        uchar byte0 = repr_byte(byte_idx, hash0, main_hash, (ushort)0);
                        uchar byte1 = (byte_idx + 1 < 36)
                            ? repr_byte(byte_idx + 1, hash0, main_hash, (ushort)0)
                            : 0;

                        ushort comb = ((ushort)byte0 << 8) | (ushort)byte1;
                        uchar val6 = (uchar)((comb >> (bit_in_byte + 3)) & 0x3fu);

                        if ((val6 != CASE_VAR_ALT0[j]) && (val6 != CASE_VAR_ALT1[j])) {
                            ok_local = 0;
                            break;
                        }
                    }
                }
        #endif

                if (ok_local) {
                    uint slot = atomic_inc(found_counter);
                    if (slot < 1024u) {
                        res[slot * 4]     = (uint)iter;
                        res[slot * 4 + 1] = idx;
                        res[slot * 4 + 2] = (uint)v;
                        res[slot * 4 + 3] = (uint)hash0;
                    }
                }
            }
#else  // NEED_CRC == 1
            // Compute CRC base once with hash0=0, then sweep using XOR deltas.
            ushort crc_base = 0;
            crc_base = crc16_update(crc_base, (uchar)FLAGS_HI);
            crc_base = crc16_update(crc_base, (uchar)FLAGS_LO);
            crc_base = crc16_update(crc_base, (uchar)0);

            #pragma unroll
            for (int k = 1; k < 32; k++) {
                crc_base = crc16_update(crc_base, GET_BYTE_BE_ARRAY(main_hash, k));
            }

            // Full CRC sweep over all admissible first hash bytes.
            for (int t = 0; t < HASH0_COUNT; t++) {
                uchar hash0 = HASH0_VALUES[t];
                ushort crc = (ushort)(crc_base ^ CRC16_DELTA_POS2[(uint)hash0]);
                uchar crc_hi = (uchar)(crc >> 8);
                uchar crc_lo = (uchar)(crc & 0xffu);

                int ok_local = 1;

                // CRC-dependent byte-mask constraints: only bytes 34 and 35.
                if (PREFIX_MASK[34] && ((crc_hi & PREFIX_MASK[34]) != PREFIX_VAL[34])) {
                    ok_local = 0;
                }
                if (ok_local && PREFIX_MASK[35] && ((crc_lo & PREFIX_MASK[35]) != PREFIX_VAL[35])) {
                    ok_local = 0;
                }

        #if N_CASE_VAR > 0
                if (ok_local) {
                    #pragma unroll
                    for (int j = 0; j < N_CASE_VAR; j++) {
                        ushort bit = CASE_VAR_BITPOS[j];
                        int byte_idx = (int)(bit >> 3);
                        int bit_in_byte = 7 - (int)(bit & 7);

                        uchar byte0 = repr_byte(byte_idx, hash0, main_hash, crc);
                        uchar byte1 = (byte_idx + 1 < 36)
                            ? repr_byte(byte_idx + 1, hash0, main_hash, crc)
                            : 0;

                        ushort comb = ((ushort)byte0 << 8) | (ushort)byte1;
                        uchar val6 = (uchar)((comb >> (bit_in_byte + 3)) & 0x3fu);

                        if ((val6 != CASE_VAR_ALT0[j]) && (val6 != CASE_VAR_ALT1[j])) {
                            ok_local = 0;
                            break;
                        }
                    }
                }
        #endif

                if (ok_local) {
                    uint slot = atomic_inc(found_counter);
                    if (slot < 1024u) {
                        res[slot * 4]     = (uint)iter;
                        res[slot * 4 + 1] = idx;
                        res[slot * 4 + 2] = (uint)v;
                        res[slot * 4 + 3] = (uint)hash0;
                    }
                }
            }
#endif
        }
    }
}
