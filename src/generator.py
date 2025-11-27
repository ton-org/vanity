"""
GPU vanity address generator (v2).

Goals for this rewrite:
- Keep the CLI surface identical to v1 (`--owner`, `--start`, `--end`, `--masterchain`,
  `--non-bounceable`, `--testnet`, `--case-sensitive`, `--only-one`).
- Make the host code "smart" and the kernel "dumb": all mapping of base64 patterns to
  byte-level masks happens here; the kernel only enforces masks and computes hashes.
- Remove warm‑up / autotune loops; pick deterministic per‑device parameters instead.
- Only touch kernel logic where it depends on the new host assumptions (first hash byte
  rewrite + CRC check ordering).

The script generates TON vanity addresses by brute‑forcing the 128‑bit salt used inside
the vanity contract. The search is offloaded to OpenCL; each hit is fully re‑validated on
the host before being written to `addresses.jsonl`.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import struct
import sys
import time
from dataclasses import dataclass
from threading import Lock, Thread
from typing import List, Optional, Sequence, Tuple

import numpy as np
import pyopencl as cl

# -----------------------------------------------------------------------------
# CLI and shared dataclasses
# -----------------------------------------------------------------------------


@dataclass
class CliConfig:
    owner: str
    start: Optional[str]
    end: Optional[str]
    masterchain: bool
    non_bounceable: bool
    testnet: bool
    case_sensitive: bool
    only_one: bool


@dataclass
class AddressParams:
    flags_byte: int
    wc_byte: int
    prefix_bits: List[int]  # 16 bits: flags + workchain (big-endian inside each byte)


@dataclass
class KernelConfig:
    flags_hi: int
    flags_lo: int
    free_hash_mask: int
    free_hash_val: int
    prefix_mask: List[int]
    prefix_val: List[int]
    has_crc: int
    prefix_pos: List[int]
    prefix_pos_nocrc: List[int]
    stateinit_variants: List[bytes]
    stateinit_prefix_lens: List[int]
    stateinit_prefix_max_len: int
    stateinit_prefix_padded: List[bytes]
    prefix_w_matrix: List[List[int]]
    code_prefix_bytes: bytes
    code_state_base: List[int]
    crc16_table: List[int]
    fixed_prefix_lengths: List[Optional[int]]
    special_variants: List[Optional[Tuple[int, int]]]
    ci_bitpos: List[int]
    ci_alt0: List[int]
    ci_alt1: List[int]


@dataclass
class DeviceParams:
    global_threads: int
    local_size: Optional[int]
    iterations: int


@dataclass
class SearchStats:
    speed_raw: float = 0.0
    speed_eff: float = 0.0
    batch_time: float = 0.0
    found: int = 0
    threads: int = 0
    iterations: int = 0
    local: Optional[int] = None
    variants: int = 0
    updated: float = 0.0


# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

PRINT_INTERVAL = 1.0  # seconds between status lines
RES_SLOTS = 1024
RES_SLOT_WORDS = 3
RES_WORDS = RES_SLOTS * RES_SLOT_WORDS

# Address layout constants (bytes and bits)
TOTAL_BYTES = 36
TOTAL_BITS = TOTAL_BYTES * 8  # 288
HASH_BIT_START = 16
HASH_BIT_END = HASH_BIT_START + 256  # exclusive

# Contract constants (pulled from v1 code)
CONST1 = 1065632427291681  # 50 bits
CONST2 = 457587318777827214152676959512820176586892797206855680  # 179 bits

# SHA-256 round constants
K_SHA256 = [
    0x428A2F98,
    0x71374491,
    0xB5C0FBCF,
    0xE9B5DBA5,
    0x3956C25B,
    0x59F111F1,
    0x923F82A4,
    0xAB1C5ED5,
    0xD807AA98,
    0x12835B01,
    0x243185BE,
    0x550C7DC3,
    0x72BE5D74,
    0x80DEB1FE,
    0x9BDC06A7,
    0xC19BF174,
    0xE49B69C1,
    0xEFBE4786,
    0x0FC19DC6,
    0x240CA1CC,
    0x2DE92C6F,
    0x4A7484AA,
    0x5CB0A9DC,
    0x76F988DA,
    0x983E5152,
    0xA831C66D,
    0xB00327C8,
    0xBF597FC7,
    0xC6E00BF3,
    0xD5A79147,
    0x06CA6351,
    0x14292967,
    0x27B70A85,
    0x2E1B2138,
    0x4D2C6DFC,
    0x53380D13,
    0x650A7354,
    0x766A0ABB,
    0x81C2C92E,
    0x92722C85,
    0xA2BFE8A1,
    0xA81A664B,
    0xC24B8B70,
    0xC76C51A3,
    0xD192E819,
    0xD6990624,
    0xF40E3585,
    0x106AA070,
    0x19A4C116,
    0x1E376C08,
    0x2748774C,
    0x34B0BCB5,
    0x391C0CB3,
    0x4ED8AA4A,
    0x5B9CCA4F,
    0x682E6FF3,
    0x748F82EE,
    0x78A5636F,
    0x84C87814,
    0x8CC70208,
    0x90BEFFFA,
    0xA4506CEB,
    0xBEF9A3F7,
    0xC67178F2,
]


# -----------------------------------------------------------------------------
# Basic helpers
# -----------------------------------------------------------------------------


def die(msg: str):
    print(msg, file=sys.stderr)
    sys.exit(1)


def int_to_bits(x: int, n: int) -> List[int]:
    """Return n high-to-low bits of integer x (big-endian bit order)."""
    return [(x >> (n - 1 - i)) & 1 for i in range(n)]


def bits_from_byte(b: int) -> List[int]:
    return [(b >> (7 - i)) & 1 for i in range(8)]


def base64url_value(ch: str) -> int:
    o = ord(ch)
    if 65 <= o <= 90:  # A-Z
        return o - 65
    if 97 <= o <= 122:  # a-z
        return o - 97 + 26
    if 48 <= o <= 57:  # 0-9
        return o - 48 + 52
    if ch == "-":
        return 62
    if ch == "_":
        return 63
    raise ValueError(f"Invalid base64url character: {ch}")


def base64url_bits(ch: str) -> List[int]:
    """6 high-to-low bits of a single base64url character."""
    v = base64url_value(ch)
    return [(v >> (5 - j)) & 1 for j in range(6)]


def char_variants(ch: str, case_sensitive: bool) -> List[str]:
    """Return allowed character variants for case-insensitive matching."""
    if case_sensitive:
        return [ch]
    if ch.isalpha():
        return list({ch.lower(), ch.upper()})
    return [ch]


def char_bit_variants(ch: str, case_sensitive: bool) -> List[List[int]]:
    """All 6-bit patterns allowed for this character given case sensitivity."""
    return [base64url_bits(v) for v in char_variants(ch, case_sensitive)]


def is_base64url(s: str) -> bool:
    return all(c.isalnum() or c in "-_" for c in s)


def bits_to_padded_bytes(bits: Sequence[int]) -> bytes:
    """TON padding: add 1 then zeros to byte boundary."""
    byte_len = (len(bits) + 7) // 8
    if byte_len == 0:
        return b""

    padded = list(bits)
    padding = byte_len * 8 - len(bits)
    if padding:
        padded.append(1)
        padded.extend([0] * (padding - 1))

    out = []
    for i in range(0, len(padded), 8):
        val = 0
        for bit in padded[i : i + 8]:
            val = (val << 1) | bit
        out.append(val)
    return bytes(out)


def crc16_table() -> List[int]:
    poly = 0x1021
    table = []
    for i in range(256):
        crc = i << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
        table.append(crc)
    return table


def crc16(data: bytes, table: Sequence[int]) -> int:
    crc = 0
    for b in data:
        crc = ((crc << 8) ^ table[((crc >> 8) ^ b) & 0xFF]) & 0xFFFF
    return crc


# -----------------------------------------------------------------------------
# TON-specific builders (code cell and stateinit prefixes)
# -----------------------------------------------------------------------------


def _rotr(x, n):
    return ((x >> n) | ((x & 0xFFFFFFFF) << (32 - n))) & 0xFFFFFFFF


def _shr(x, n):
    return (x & 0xFFFFFFFF) >> n


def _sigma0(x):
    return _rotr(x, 7) ^ _rotr(x, 18) ^ _shr(x, 3)


def _sigma1(x):
    return _rotr(x, 17) ^ _rotr(x, 19) ^ _shr(x, 10)


def _Sigma0(x):
    return _rotr(x, 2) ^ _rotr(x, 13) ^ _rotr(x, 22)


def _Sigma1(x):
    return _rotr(x, 6) ^ _rotr(x, 11) ^ _rotr(x, 25)


def sha256_compress_block(block: bytes, state=None) -> List[int]:
    """Single SHA-256 compression on one 64-byte block."""
    assert len(block) == 64, "Block must be exactly 64 bytes"

    if state is None:
        a, b, c, d, e, f, g, h = (
            0x6A09E667,
            0xBB67AE85,
            0x3C6EF372,
            0xA54FF53A,
            0x510E527F,
            0x9B05688C,
            0x1F83D9AB,
            0x5BE0CD19,
        )
    else:
        a, b, c, d, e, f, g, h = state

    w = [0] * 64
    for i in range(16):
        (w[i],) = struct.unpack(">I", block[i * 4 : (i + 1) * 4])
    for i in range(16, 64):
        w[i] = (
            _sigma1(w[i - 2]) + w[i - 7] + _sigma0(w[i - 15]) + w[i - 16]
        ) & 0xFFFFFFFF

    for i in range(64):
        t1 = (h + _Sigma1(e) + ((e & f) ^ (~e & g)) + K_SHA256[i] + w[i]) & 0xFFFFFFFF
        t2 = (_Sigma0(a) + ((a & b) ^ (a & c) ^ (b & c))) & 0xFFFFFFFF
        h = g
        g = f
        f = e
        e = (d + t1) & 0xFFFFFFFF
        d = c
        c = b
        b = a
        a = (t1 + t2) & 0xFFFFFFFF

    return [
        (state[0] + a) & 0xFFFFFFFF if state else (0x6A09E667 + a) & 0xFFFFFFFF,
        (state[1] + b) & 0xFFFFFFFF if state else (0xBB67AE85 + b) & 0xFFFFFFFF,
        (state[2] + c) & 0xFFFFFFFF if state else (0x3C6EF372 + c) & 0xFFFFFFFF,
        (state[3] + d) & 0xFFFFFFFF if state else (0xA54FF53A + d) & 0xFFFFFFFF,
        (state[4] + e) & 0xFFFFFFFF if state else (0x510E527F + e) & 0xFFFFFFFF,
        (state[5] + f) & 0xFFFFFFFF if state else (0x9B05688C + f) & 0xFFFFFFFF,
        (state[6] + g) & 0xFFFFFFFF if state else (0x1F83D9AB + g) & 0xFFFFFFFF,
        (state[7] + h) & 0xFFFFFFFF if state else (0x5BE0CD19 + h) & 0xFFFFFFFF,
    ]


def owner_bits(owner_raw: bytes) -> List[int]:
    """Bits of MsgAddressInt: tag(2), anycast(1), workchain(8), addr hash(256)."""
    workchain = owner_raw[1]
    addr_hash = owner_raw[2:34]

    bits: List[int] = [1, 0]  # tag
    bits.append(0)  # anycast none

    wc_signed = workchain if workchain < 128 else workchain - 256
    wc_byte = wc_signed & 0xFF
    bits.extend(bits_from_byte(wc_byte))

    for b in addr_hash:
        bits.extend(bits_from_byte(b))

    assert len(bits) == 267, "Unexpected owner bits length"
    return bits


def build_code_repr(owner_raw: bytes, salt_16: bytes) -> bytes:
    """Serialize code cell: const bits + owner + const + salt (total 80 bytes)."""
    assert len(salt_16) == 16, "Salt must be 16 bytes (128 bits)"

    bits: List[int] = []
    bits += int_to_bits(CONST1, 50)
    bits += owner_bits(owner_raw)
    bits += int_to_bits(CONST2, 179)
    for b in salt_16:
        bits += bits_from_byte(b)

    assert len(bits) == 624, "Unexpected code bits length"

    data_bytes = []
    for i in range(0, len(bits), 8):
        val = 0
        for bit in bits[i : i + 8]:
            val = (val << 1) | bit
        data_bytes.append(val)

    b = len(bits)
    d1 = 0x00  # 0 refs
    d2 = (b // 8) + ((b + 7) // 8)  # floor(b/8) + ceil(b/8)
    return bytes([d1, d2]) + bytes(data_bytes)


def build_stateinit_prefix(
    fixed_prefix_length: Optional[int], special: Optional[Tuple[int, int]]
) -> bytes:
    """Prefix bytes (descriptors + padded bits + ref depth) of StateInit cell."""
    bits: List[int] = []

    if fixed_prefix_length is not None:
        if not (0 <= fixed_prefix_length < 32):
            raise ValueError("fixedPrefixLength must be 0..31")
        bits.append(1)
        bits += int_to_bits(fixed_prefix_length, 5)
    else:
        bits.append(0)

    if special is not None:
        tick, tock = special
        bits.append(1)
        bits.append(1 if tick else 0)
        bits.append(1 if tock else 0)
    else:
        bits.append(0)

    bits.append(1)  # code: Some
    bits.append(0)  # data: None
    bits.append(0)  # libraries: empty dict

    padded_bits = bits_to_padded_bytes(bits)
    bits_desc = ((len(bits) + 7) // 8) + (len(bits) // 8)  # ceil + floor

    d1 = 1  # ordinary cell, level mask 0, 1 ref
    d2 = bits_desc

    return bytes([d1, d2]) + padded_bits + b"\x00\x00"


def pack_prefix_words(prefix: bytes) -> List[int]:
    words = [0] * 16
    for i, b in enumerate(prefix):
        w = i >> 2
        shift = 24 - ((i & 3) * 8)
        words[w] |= int(b) << shift
    return words


def to_boc_single_cell(cell_bytes: bytes) -> bytes:
    """
    Serialize a single-root, no-refs cell into a minimal Bag of Cells (BoC)
    without index and without CRC32C, using standard TON BoC layout.
    """
    cells = 1
    roots = 1
    absent = 0
    size_bytes = max(1, (cells.bit_length() + 7) // 8)
    size_bytes = min(size_bytes, 4)

    tot_cells_size = len(cell_bytes)
    off_bytes = max(1, (tot_cells_size.bit_length() + 7) // 8)
    off_bytes = min(off_bytes, 8)

    has_idx = 0
    has_crc32c = 0
    has_cache_bits = 0
    flags = 0

    out = bytearray()
    out += b"\xb5\xee\x9c\x72"
    flags_byte = (
        (has_idx << 7)
        | (has_crc32c << 6)
        | (has_cache_bits << 5)
        | ((flags & 0x3) << 3)
        | (size_bytes & 0x7)
    )
    out.append(flags_byte)
    out.append(off_bytes)
    out += cells.to_bytes(size_bytes, "big")
    out += roots.to_bytes(size_bytes, "big")
    out += absent.to_bytes(size_bytes, "big")
    out += tot_cells_size.to_bytes(off_bytes, "big")
    out += (0).to_bytes(size_bytes, "big")  # single root with index 0
    # no index when has_idx == 0
    out += cell_bytes
    # no CRC32C when has_crc32c == 0
    return bytes(out)


# -----------------------------------------------------------------------------
# Pattern mapping host-side
# -----------------------------------------------------------------------------


def set_mask_bit(
    mask_arr: List[int], val_arr: List[int], bit_index: int, bit_value: int
):
    byte = bit_index // 8
    offset = 7 - (bit_index % 8)
    mask_arr[byte] |= 1 << offset
    if bit_value:
        val_arr[byte] |= 1 << offset


def choose_start_alignment(
    start: str, case_sensitive: bool, prefix_bits: List[int]
) -> Tuple[int, List[List[List[int]]]]:
    """
    Pick the earliest base64 digit offset where the start pattern can fit without
    contradicting fixed flag/workchain bits (bits 0..15). Returns the digit offset
    and per-character bit variants filtered to those compatible with the overlap.
    """
    if not start:
        return 0, []

    char_opts = [char_bit_variants(ch, case_sensitive) for ch in start]
    len_bits = len(start) * 6
    max_digit_offset = (TOTAL_BITS - len_bits) // 6

    for digit_offset in range(max_digit_offset + 1):
        bit_offset = 6 * digit_offset
        ok = True
        filtered: List[List[List[int]]] = []

        for ci, variants in enumerate(char_opts):
            char_bit_base = bit_offset + ci * 6
            overlap = [b for b in range(6) if char_bit_base + b < 16]
            if not overlap:
                filtered.append(variants)
                continue

            valid = []
            for var in variants:
                if all(var[b] == prefix_bits[char_bit_base + b] for b in overlap):
                    valid.append(var)
            if not valid:
                ok = False
                break
            filtered.append(valid)

        if ok:
            return digit_offset, filtered

    # Fallback: place after flags/workchain if nothing matched (should be rare)
    return (16 + 5) // 6, char_opts


def build_kernel_config(cli: CliConfig, owner_raw: bytes) -> Tuple[KernelConfig, int]:
    """Compute masks, free-byte rewrite, and stateinit constants for the kernel."""

    # Flags / workchain bytes
    flags_byte = 0x51 if cli.non_bounceable else 0x11
    if cli.testnet:
        flags_byte |= 0x80
    wc_byte = 0xFF if cli.masterchain else 0x00
    addr_params = AddressParams(
        flags_byte=flags_byte,
        wc_byte=wc_byte,
        prefix_bits=bits_from_byte(flags_byte) + bits_from_byte(wc_byte),
    )

    # Bit-level masks
    prefix_mask = [0] * TOTAL_BYTES
    prefix_val = [0] * TOTAL_BYTES

    free_mask = 0
    free_val = 0

    # Start pattern: choose digit alignment on a 6-bit boundary
    start_digit_base = 0
    ci_bitpos: List[int] = []
    ci_alt0: List[int] = []
    ci_alt1: List[int] = []

    if cli.start:
        start_digit_base, start_char_variants = choose_start_alignment(
            cli.start, cli.case_sensitive, addr_params.prefix_bits
        )
        start_len_bits = len(cli.start) * 6
        bit_offset = start_digit_base * 6

        for i in range(start_len_bits):
            char_idx = i // 6
            bit_in_char = i % 6
            variants = start_char_variants[char_idx]
            allowed_bits = {v[bit_in_char] for v in variants}
            bit_index = bit_offset + i

            # Record ambiguous (case-insensitive) chars once per char to handle in kernel
            if not cli.case_sensitive and bit_in_char == 0:
                variant_vals = {
                    sum((bit << (5 - k)) for k, bit in enumerate(v)) for v in variants
                }
                if len(variant_vals) == 2:
                    vals = list(variant_vals)
                    ci_bitpos.append(bit_index)
                    ci_alt0.append(vals[0])
                    ci_alt1.append(vals[1])

            if bit_index < 16:
                # Already satisfied by flags/workchain (checked in alignment)
                continue

            if len(allowed_bits) != 1:
                continue  # can't constrain this bit without losing variants

            bit = next(iter(allowed_bits))
            if HASH_BIT_START <= bit_index < HASH_BIT_START + 8:
                offset = 7 - (bit_index % 8)
                free_mask |= 1 << offset
                if bit:
                    free_val |= 1 << offset
            elif bit_index < TOTAL_BITS and bit_index < HASH_BIT_END:
                set_mask_bit(prefix_mask, prefix_val, bit_index, bit)

    # Suffix bits map to the tail of the address
    if cli.end:
        end_char_variants = [
            char_bit_variants(ch, cli.case_sensitive) for ch in cli.end
        ]
        end_len_bits = len(cli.end) * 6
        bit_base = TOTAL_BITS - end_len_bits

        for i in range(end_len_bits):
            char_idx = i // 6
            bit_in_char = i % 6
            variants = end_char_variants[char_idx]
            allowed_bits = {v[bit_in_char] for v in variants}
            bit_index = bit_base + i

            if not cli.case_sensitive and bit_in_char == 0:
                variant_vals = {
                    sum((bit << (5 - k)) for k, bit in enumerate(v)) for v in variants
                }
                if len(variant_vals) == 2:
                    vals = list(variant_vals)
                    ci_bitpos.append(bit_index)
                    ci_alt0.append(vals[0])
                    ci_alt1.append(vals[1])

            if bit_index < 16:
                continue  # never constrain flags/workchain in kernel
            if len(allowed_bits) != 1:
                continue

            bit = next(iter(allowed_bits))
            set_mask_bit(prefix_mask, prefix_val, bit_index, bit)

    has_crc = 1 if (prefix_mask[34] or prefix_mask[35]) else 0
    prefix_pos = [i for i, m in enumerate(prefix_mask) if m]
    prefix_pos_nocrc = [i for i in prefix_pos if i < 34]

    # StateInit variants
    fixed_prefix_lengths = [8] if cli.start else [None] + list(range(9))
    special_variants: List[Optional[Tuple[int, int]]] = [
        None,
        (0, 0),
        (0, 1),
        (1, 0),
        (1, 1),
    ]
    stateinit_variants: List[bytes] = []
    stateinit_prefix_lens: List[int] = []
    for fpl in fixed_prefix_lengths:
        for spec in special_variants:
            prefix = build_stateinit_prefix(fpl, spec)
            stateinit_variants.append(prefix)
            stateinit_prefix_lens.append(len(prefix))

    stateinit_prefix_max_len = max(stateinit_prefix_lens)
    stateinit_prefix_padded = [
        p + b"\x00" * (stateinit_prefix_max_len - len(p)) for p in stateinit_variants
    ]
    prefix_w_matrix = [pack_prefix_words(p) for p in stateinit_variants]

    # Code prefix and IV after first block
    zero_salt = b"\x00" * 16
    code_repr_zero = build_code_repr(owner_raw, zero_salt)
    code_prefix_bytes = code_repr_zero[:64]
    code_state_base = sha256_compress_block(code_prefix_bytes)

    crc_table = crc16_table()

    kernel_cfg = KernelConfig(
        flags_hi=flags_byte,
        flags_lo=wc_byte,
        free_hash_mask=free_mask,
        free_hash_val=free_val,
        prefix_mask=prefix_mask,
        prefix_val=prefix_val,
        has_crc=has_crc,
        prefix_pos=prefix_pos,
        prefix_pos_nocrc=prefix_pos_nocrc,
        stateinit_variants=stateinit_variants,
        stateinit_prefix_lens=stateinit_prefix_lens,
        stateinit_prefix_max_len=stateinit_prefix_max_len,
        stateinit_prefix_padded=stateinit_prefix_padded,
        prefix_w_matrix=prefix_w_matrix,
        code_prefix_bytes=code_prefix_bytes,
        code_state_base=code_state_base,
        crc16_table=crc_table,
        fixed_prefix_lengths=fixed_prefix_lengths,
        special_variants=special_variants,
        ci_bitpos=ci_bitpos,
        ci_alt0=ci_alt0,
        ci_alt1=ci_alt1,
    )

    # Start string alignment inside the friendly address
    return kernel_cfg, start_digit_base


# -----------------------------------------------------------------------------
# Kernel rendering
# -----------------------------------------------------------------------------


def render_kernel(kernel_cfg: KernelConfig) -> str:
    kernel_path = os.path.join(os.path.dirname(__file__), "kernel.cl")
    with open(kernel_path, "r", encoding="utf-8") as f:
        src = f.read()

    def repl(tag: str, value: str):
        nonlocal src
        src = src.replace(tag, value)

    repl(
        "<<CODE_PREFIX_BYTES>>", ", ".join(str(b) for b in kernel_cfg.code_prefix_bytes)
    )
    repl(
        "<<CODE_STATE_BASE>>",
        ", ".join(f"0x{w:08x}u" for w in kernel_cfg.code_state_base),
    )
    repl("<<CRC16_TABLE>>", ", ".join(str(c) for c in kernel_cfg.crc16_table))
    repl(
        "<<PREFIX_W_MATRIX>>",
        ",\n    ".join(
            "{ " + ", ".join(str(w) for w in row) + " }"
            for row in kernel_cfg.prefix_w_matrix
        ),
    )
    repl("<<PREFIX_MASK>>", ", ".join(str(b) for b in kernel_cfg.prefix_mask))
    repl("<<PREFIX_VAL>>", ", ".join(str(b) for b in kernel_cfg.prefix_val))
    repl("<<HAS_CRC_CONSTRAINT>>", str(kernel_cfg.has_crc))
    repl("<<N_ACTIVE>>", str(len(kernel_cfg.prefix_pos)))
    repl("<<N_ACTIVE_NOCRC>>", str(len(kernel_cfg.prefix_pos_nocrc)))
    repl("<<PREFIX_POS>>", ", ".join(str(i) for i in kernel_cfg.prefix_pos))
    repl("<<PREFIX_POS_NOCRC>>", ", ".join(str(i) for i in kernel_cfg.prefix_pos_nocrc))
    repl("<<N_CASE_INSENSITIVE>>", str(len(kernel_cfg.ci_bitpos)))
    repl("<<CASE_BITPOS>>", ", ".join(str(b) for b in kernel_cfg.ci_bitpos))
    repl("<<CASE_ALT0>>", ", ".join(str(v) for v in kernel_cfg.ci_alt0))
    repl("<<CASE_ALT1>>", ", ".join(str(v) for v in kernel_cfg.ci_alt1))
    repl("<<N_STATEINIT_VARIANTS>>", str(len(kernel_cfg.stateinit_variants)))
    repl("<<STATEINIT_PREFIX_MAX_LEN>>", str(kernel_cfg.stateinit_prefix_max_len))
    repl(
        "<<STATEINIT_PREFIX_MATRIX>>",
        ",\n    ".join(
            "{ " + ", ".join(str(b) for b in row) + " }"
            for row in kernel_cfg.stateinit_prefix_padded
        ),
    )
    repl(
        "<<STATEINIT_PREFIX_LENS>>",
        ", ".join(str(length) for length in kernel_cfg.stateinit_prefix_lens),
    )
    repl("<<FLAGS_HI>>", str(kernel_cfg.flags_hi))
    repl("<<FLAGS_LO>>", str(kernel_cfg.flags_lo))
    repl("<<FREE_HASH_MASK>>", str(kernel_cfg.free_hash_mask))
    repl("<<FREE_HASH_VAL>>", str(kernel_cfg.free_hash_val))

    return src


# -----------------------------------------------------------------------------
# Device heuristics (no autotune)
# -----------------------------------------------------------------------------


def pick_device_params(device: cl.Device, n_variants: int) -> DeviceParams:
    vendor = device.vendor.lower()
    cu = device.max_compute_units or 1

    if "nvidia" in vendor:
        base_threads = cu * 2048
        local = 256
        iters = 4096
    elif "advanced micro devices" in vendor or "amd" in vendor:
        base_threads = cu * 2048
        local = 256
        iters = 4096
    elif "apple" in vendor:
        base_threads = cu * 1024
        local = 256
        iters = 2048
    else:  # intel / others / cpu
        base_threads = cu * 1024
        local = 128
        iters = 2048

    if n_variants > 0:
        iters = max(512, int(iters / n_variants))

    local = min(local, device.max_work_group_size)

    return DeviceParams(global_threads=base_threads, local_size=local, iterations=iters)


# -----------------------------------------------------------------------------
# Core solver
# -----------------------------------------------------------------------------


class SearchContext:
    def __init__(
        self,
        kernel_cfg: KernelConfig,
        cli: CliConfig,
        owner_raw: bytes,
        start_digit_base: int,
    ):
        self.kernel_cfg = kernel_cfg
        self.cli = cli
        self.owner_raw = owner_raw
        self.start_digit_base = start_digit_base
        self.crc_table = kernel_cfg.crc16_table
        self.stop_flag = False
        self.n_found = 0
        self.total_iters = 0.0
        self.status = SearchStats(variants=len(kernel_cfg.stateinit_variants))
        self.status_lock = Lock()
        self.output_lock = Lock()
        self.output_file = open("addresses.jsonl", "a", encoding="utf-8")


def process_hit(
    ctx: SearchContext,
    base_salt: bytes,
    iter_idx: int,
    idx: int,
    variant_idx: int,
) -> tuple[bool, str]:
    """Rebuild candidate, verify, and persist. Returns (ok, reason)."""

    cfg = ctx.kernel_cfg
    cli = ctx.cli

    if variant_idx >= len(cfg.stateinit_variants):
        return False, "variant_idx out of range"

    salt_bytes = bytearray(base_salt)
    salt_words = np.frombuffer(salt_bytes, dtype=np.uint32)
    salt_words[0] ^= np.uint32(iter_idx)
    salt_words[1] ^= np.uint32(idx)

    code_repr = build_code_repr(ctx.owner_raw, bytes(salt_bytes))
    code_hash = hashlib.sha256(code_repr).digest()

    prefix = cfg.stateinit_variants[variant_idx]
    main_data = bytearray(prefix)
    main_data.extend(code_hash)
    main_hash = hashlib.sha256(main_data).digest()

    repr_bytes = bytearray(TOTAL_BYTES)
    repr_bytes[0] = cfg.flags_hi
    repr_bytes[1] = cfg.flags_lo

    # Rewrite first hash byte with free bits
    hash0 = main_hash[0]
    hash0 = (hash0 & (~cfg.free_hash_mask & 0xFF)) | (
        cfg.free_hash_val & cfg.free_hash_mask
    )
    repr_bytes[2] = hash0
    repr_bytes[3:34] = main_hash[1:32]

    crc_val = crc16(bytes(repr_bytes[:34]), ctx.crc_table)
    repr_bytes[34] = (crc_val >> 8) & 0xFF
    repr_bytes[35] = crc_val & 0xFF

    # Byte-mask validation (identical to kernel constraints)
    for i, m in enumerate(cfg.prefix_mask):
        if m and (repr_bytes[i] & m) != cfg.prefix_val[i]:
            return False, "prefix mask mismatch"

    # String-level validation
    addr_str = base64.urlsafe_b64encode(bytes(repr_bytes)).decode("utf-8")

    if cli.start:
        slice_start = addr_str[
            ctx.start_digit_base : ctx.start_digit_base + len(cli.start)
        ]
        if cli.case_sensitive:
            if slice_start != cli.start:
                return False, "start mismatch"
        else:
            if slice_start.lower() != cli.start.lower():
                return False, "start mismatch"

    if cli.end:
        slice_end = addr_str[-len(cli.end) :]
        if cli.case_sensitive:
            if slice_end != cli.end:
                return False, "end mismatch"
        else:
            if slice_end.lower() != cli.end.lower():
                return False, "end mismatch"

    # Build output objects
    split_idx = variant_idx // len(cfg.special_variants)
    special_idx = variant_idx % len(cfg.special_variants)
    fpl_val = cfg.fixed_prefix_lengths[split_idx]
    special = cfg.special_variants[special_idx]
    boc_code = to_boc_single_cell(code_repr)

    init_obj = {
        "code": base64.urlsafe_b64encode(boc_code).decode("utf-8"),
        "fixedPrefixLength": 0 if fpl_val is None else fpl_val,
        "special": None
        if special is None
        else {"tick": bool(special[0]), "tock": bool(special[1])},
    }

    config_obj = {
        "owner": cli.owner,
        "start": cli.start,
        "end": cli.end,
        "masterchain": cli.masterchain,
        "non_bounceable": cli.non_bounceable,
        "testnet": cli.testnet,
        "case_sensitive": cli.case_sensitive,
        "only_one": cli.only_one,
    }

    entry = {
        "address": addr_str,
        "init": init_obj,
        "config": config_obj,
        "timestamp": time.time(),
    }

    with ctx.output_lock:
        ctx.output_file.write(json.dumps(entry, separators=(",", ":")) + "\n")
        ctx.output_file.flush()
    ctx.n_found += 1
    return True, "ok"


def device_thread(
    dev: cl.Device, context: cl.Context, program: cl.Program, ctx: SearchContext
):
    cfg = ctx.kernel_cfg
    params = pick_device_params(dev, len(cfg.stateinit_variants))

    queue = cl.CommandQueue(context, device=dev)
    kernel = cl.Kernel(program, "hash_main")

    mf = cl.mem_flags
    res_host = np.zeros(RES_WORDS, dtype=np.uint32)
    res_g = cl.Buffer(context, mf.READ_WRITE, size=res_host.nbytes)
    found_count_host = np.zeros(1, dtype=np.uint32)
    found_count_g = cl.Buffer(
        context, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=found_count_host
    )

    while not ctx.stop_flag:
        base_salt = os.urandom(16)
        salt_words = np.frombuffer(base_salt, dtype=np.uint32)

        # reset counter
        cl.enqueue_fill_buffer(queue, found_count_g, np.uint32(0), 0, 4)

        start = time.time()

        local_shape = None if params.local_size is None else (params.local_size,)
        kernel(
            queue,
            (params.global_threads,),
            local_shape,
            np.int32(params.iterations),
            np.uint32(salt_words[0]),
            np.uint32(salt_words[1]),
            np.uint32(salt_words[2]),
            np.uint32(salt_words[3]),
            found_count_g,
            res_g,
        ).wait()

        cl.enqueue_copy(queue, found_count_host, found_count_g).wait()
        count = int(found_count_host[0])

        if count > 0:
            cl.enqueue_copy(queue, res_host, res_g).wait()
            for slot in range(min(count, RES_SLOTS)):
                iter_idx = int(res_host[slot * RES_SLOT_WORDS + 0])
                idx = int(res_host[slot * RES_SLOT_WORDS + 1])
                variant_idx = int(res_host[slot * RES_SLOT_WORDS + 2])
                ok, reason = process_hit(ctx, base_salt, iter_idx, idx, variant_idx)
                if not ok:
                    print(
                        f"Validation failed: {reason} (iter={iter_idx}, idx={idx}, variant={variant_idx})",
                        flush=True,
                    )
                    ctx.stop_flag = True
                    raise RuntimeError(f"Validation failed: {reason}")
                if ctx.cli.only_one and ctx.n_found > 0:
                    ctx.stop_flag = True
                    break

        elapsed = time.time() - start
        total_batch_iters = (
            params.global_threads * params.iterations * len(cfg.stateinit_variants)
        )
        speed_raw = (
            params.global_threads * params.iterations / elapsed / 1e6
            if elapsed > 0
            else 0.0
        )
        speed_eff = speed_raw * len(cfg.stateinit_variants)

        with ctx.status_lock:
            ctx.status.speed_raw = speed_raw
            ctx.status.speed_eff = speed_eff
            ctx.status.batch_time = elapsed
            ctx.total_iters += total_batch_iters
            # misses are now fatal; keep zero
            ctx.status.found = ctx.n_found
            ctx.status.threads = params.global_threads
            ctx.status.iterations = params.iterations
            ctx.status.local = params.local_size
            ctx.status.updated = time.time()


def reporter_thread(ctx: SearchContext):
    history = []  # (timestamp, eff_hps, found_total)

    def fmt_rate(hps: float) -> str:
        units = [
            (1e12, "T"),
            (1e9, "B"),
            (1e6, "M"),
            (1e3, "k"),
        ]
        for factor, label in units:
            if hps >= factor:
                return f"{hps / factor:.2f}{label}"
        return f"{hps:.2f}"

    def add_history(ts: float, eff: float, found: float):
        history.append((ts, eff, found))
        cutoff = ts - 20.0
        while history and history[0][0] < cutoff:
            history.pop(0)

    def avg_rates():
        if not history:
            return 0.0, 0.0
        eff_avg = sum(h[1] for h in history) / len(history)
        # derivative of found over window
        if len(history) >= 2:
            f0 = history[0][2]
            f1 = history[-1][2]
            t0 = history[0][0]
            t1 = history[-1][0]
            found_rate = (f1 - f0) / max(1e-6, (t1 - t0))
        else:
            found_rate = 0.0
        return eff_avg, found_rate

    while not ctx.stop_flag:
        with ctx.status_lock:
            snap = SearchStats(**ctx.status.__dict__)
        if ctx.total_iters <= 0:
            time.sleep(PRINT_INTERVAL)
            continue

        eff = snap.speed_eff * 1e6  # h/s
        add_history(snap.updated, eff, snap.found)
        eff_avg, found_rate_10s = avg_rates()

        green = "\x1b[32m"
        cyan = "\x1b[36m"
        dim = "\x1b[2m"
        reset = "\x1b[0m"
        fr_part = f" ({found_rate_10s:,.2f}/s)" if found_rate_10s > 1 else ""
        found_color = green if snap.found > 0 else "\x1b[37m"
        msg = (
            f"{found_color}Found {snap.found:,}{reset}{fr_part}, "
            f"{dim}{cyan}{fmt_rate(eff_avg)} iters/s{reset}"
        )
        print(msg, flush=True)
        time.sleep(PRINT_INTERVAL)


# -----------------------------------------------------------------------------
# CLI parsing and main
# -----------------------------------------------------------------------------


def parse_cli() -> CliConfig:
    parser = argparse.ArgumentParser(
        prog="vanity-generator",
        description="Generate beautiful TON wallet addresses on GPU using the vanity contract.",
        usage="%(prog)s --owner OWNER [--start PREFIX] [--end SUFFIX] [options]",
    )
    parser._optionals.title = "Options"

    parser.add_argument(
        "-o",
        "--owner",
        required=True,
        help="Base64url owner address for the vanity contract",
    )
    parser.add_argument(
        "-s",
        "--start",
        type=str,
        default=None,
        help="Address prefix to match, base64url",
    )
    parser.add_argument(
        "-e", "--end", type=str, default=None, help="Address suffix to match, base64url"
    )
    parser.add_argument(
        "-m",
        "--masterchain",
        action="store_true",
        help="Use masterchain (workchain -1) instead of basechain",
    )
    parser.add_argument(
        "-n",
        "--non-bounceable",
        action="store_true",
        help="Search for non-bounceable addresses instead of bounceable",
    )
    parser.add_argument(
        "-t", "--testnet", action="store_true", help="Search for testnet addresses"
    )
    parser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="Treat prefix/suffix matching as case-sensitive",
    )
    parser.add_argument(
        "--only-one",
        action="store_true",
        help="Stop after the first matching address is found",
    )

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    if not args.start and not args.end:
        parser.print_usage()
        print("vanity-generator: error: at least one of --start or --end is required")
        sys.exit(0)

    if not is_base64url(args.owner):
        die("--owner must be base64url (no padding)")

    try:
        owner_raw = base64.urlsafe_b64decode(args.owner + "==")
    except Exception:
        die("--owner is not valid base64url")
    if len(owner_raw) < 34:
        die("--owner decoded payload is too short (expected friendly address)")

    if args.start and not is_base64url(args.start):
        die("--start must contain only base64url characters")
    if args.end and not is_base64url(args.end):
        die("--end must contain only base64url characters")

    return CliConfig(
        owner=args.owner,
        start=args.start,
        end=args.end,
        masterchain=bool(args.masterchain),
        non_bounceable=bool(args.non_bounceable),
        testnet=bool(args.testnet),
        case_sensitive=bool(args.case_sensitive),
        only_one=bool(args.only_one),
    )


def main():
    cli = parse_cli()
    owner_raw = base64.urlsafe_b64decode(cli.owner + "==")

    kernel_cfg, start_digit_base = build_kernel_config(cli, owner_raw)
    kernel_src = render_kernel(kernel_cfg)

    platforms = cl.get_platforms()
    devices_used = []
    threads = []

    ctx = SearchContext(kernel_cfg, cli, owner_raw, start_digit_base)

    def attach_devices(devices: List[cl.Device]):
        nonlocal devices_used, threads
        if not devices:
            return
        context = cl.Context(devices=devices)
        program = cl.Program(context, kernel_src).build()
        for dev in devices:
            print(f"Using device: {dev.name}")
            t = Thread(
                target=device_thread,
                args=(dev, context, program, ctx),
                name=f"dev-{dev.name}",
            )
            t.start()
            threads.append(t)
            devices_used.append(dev)

    # Prefer GPUs, but fall back to any OpenCL device if none are available
    for platform in platforms:
        attach_devices(platform.get_devices(cl.device_type.GPU))

    if not devices_used:
        for platform in platforms:
            attach_devices(platform.get_devices(cl.device_type.ALL))

    if not devices_used:
        die("No OpenCL devices found")

    reporter = Thread(target=reporter_thread, args=(ctx,), name="reporter", daemon=True)
    reporter.start()

    try:
        while not ctx.stop_flag:
            alive = False
            for t in threads:
                t.join(1)
                alive = alive or t.is_alive()
            if not alive:
                break
    except KeyboardInterrupt:
        print("Interrupted")
        ctx.stop_flag = True
    finally:
        ctx.stop_flag = True
        for t in threads:
            t.join()
        reporter.join()
        ctx.output_file.close()


if __name__ == "__main__":
    main()
