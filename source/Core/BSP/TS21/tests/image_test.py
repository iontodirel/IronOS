import struct
import unittest

from tools import generate_font, inspect_image


def jal(displacement):
    return (
        ((displacement >> 20) & 1) << 31
        | ((displacement >> 1) & 0x3FF) << 21
        | ((displacement >> 11) & 1) << 20
        | ((displacement >> 12) & 0xFF) << 12
        | 0x6F
    )


def image():
    start = inspect_image.APP_START
    payload = bytearray(272)
    struct.pack_into("<I", payload, 0, jal(260))
    struct.pack_into("<I", payload, 4, start)
    for vector in range(1, 64):
        struct.pack_into("<I", payload, 4 + vector * 4, start + 264)
    struct.pack_into("<II", payload, 260, 0x13, 0x13)
    header = inspect_image.ELF_HEADER.pack(
        b"\x7fELF\x01\x01\x01" + bytes(9),
        2,
        243,
        1,
        start,
        52,
        0,
        1,
        52,
        32,
        2,
        0,
        0,
        0,
    )
    flash = inspect_image.PROGRAM_HEADER.pack(
        1, 256, start, start, len(payload), len(payload), 5, 4
    )
    ram = inspect_image.PROGRAM_HEADER.pack(
        1, 0, inspect_image.RAM_START, inspect_image.RAM_START, 0, 1024, 6, 4
    )
    data = bytearray(header + flash + ram)
    data.extend(bytes(256 - len(data)))
    data.extend(payload)
    return data


class ImageTests(unittest.TestCase):
    def test_valid_layout(self):
        report = inspect_image.inspect(image())
        self.assertEqual(report["entry"], "0x08007000")
        self.assertEqual(report["vector_base"], "0x08007004")
        self.assertEqual(report["flash_loaded_bytes"], 272)
        self.assertEqual(report["ram_static_bytes"], 1024)
        self.assertEqual(report["status"], "layout-valid; hardware-unvalidated")

    def reject_u32(self, offset, value):
        data = image()
        struct.pack_into("<I", data, offset, value)
        with self.assertRaises(ValueError):
            inspect_image.inspect(data)

    def test_bootloader_entry_rejected(self):
        self.reject_u32(24, 0x08000000)

    def test_bootloader_load_rejected(self):
        self.reject_u32(52 + 12, 0x08006000)

    def test_settings_load_rejected(self):
        self.reject_u32(52 + 12, 0x0800FC00)

    def test_ram_stack_overlap_rejected(self):
        self.reject_u32(84 + 20, 0x5000)

    def test_outside_ram_rejected(self):
        self.reject_u32(84 + 8, 0x20010000)

    def test_truncated_file_rejected(self):
        for size in (0, 51, 60, 115, 270, 527):
            with self.subTest(size=size), self.assertRaises(ValueError):
                inspect_image.inspect(image()[:size])

    def test_invalid_machine_rejected(self):
        data = image()
        struct.pack_into("<H", data, 18, 40)
        with self.assertRaises(ValueError):
            inspect_image.inspect(data)

    def test_float_abi_rejected(self):
        self.reject_u32(36, 5)

    def test_bad_reset_instruction_rejected(self):
        self.reject_u32(256, 0x13)

    def test_reset_jump_to_bootloader_rejected(self):
        self.reject_u32(256, jal(-4))

    def test_bad_reset_vector_rejected(self):
        self.reject_u32(260, 0x08000000)

    def test_bad_interrupt_vector_rejected(self):
        self.reject_u32(264, 0x08006A30)

    def test_unmapped_interrupt_vector_rejected(self):
        self.reject_u32(264, 0x0800E000)

    def test_filesz_larger_than_memsz_rejected(self):
        self.reject_u32(52 + 20, 1)

    def test_invalid_alignment_rejected(self):
        self.reject_u32(52 + 28, 3)

    def test_initialized_data_loaded_into_ram(self):
        data = image()
        data[84:116] = inspect_image.PROGRAM_HEADER.pack(
            1,
            len(data),
            inspect_image.RAM_START,
            inspect_image.APP_START + 272,
            16,
            1024,
            6,
            4,
        )
        data.extend(bytes(16))
        report = inspect_image.inspect(data)
        self.assertEqual(report["flash_loaded_bytes"], 288)
        self.assertEqual(report["flash_end_exclusive"], "0x08007120")
        self.assertEqual(report["ram_static_bytes"], 1024)

    def test_overlapping_flash_segments_rejected(self):
        data = image()
        address = inspect_image.APP_START + 4
        data[84:116] = inspect_image.PROGRAM_HEADER.pack(
            1, 256, address, address, 8, 8, 4, 4
        )
        with self.assertRaisesRegex(ValueError, "Overlapping load segments"):
            inspect_image.inspect(data)

    def test_flash_budget_boundary(self):
        data = image()
        budget = inspect_image.FLASH_END - inspect_image.APP_START
        data.extend(bytes(budget - 272))
        struct.pack_into("<II", data, 52 + 16, budget, budget)
        self.assertEqual(
            inspect_image.inspect(data)["flash_end_exclusive"], "0x0800FC00"
        )
        data.append(0)
        struct.pack_into("<II", data, 52 + 16, budget + 1, budget + 1)
        with self.assertRaisesRegex(ValueError, "outside application flash/RAM"):
            inspect_image.inspect(data)

    def test_ram_stack_boundary(self):
        data = image()
        capacity = inspect_image.STACK_BOTTOM - inspect_image.RAM_START
        struct.pack_into("<I", data, 84 + 20, capacity)
        self.assertEqual(inspect_image.inspect(data)["ram_static_bytes"], capacity)
        struct.pack_into("<I", data, 84 + 20, capacity + 1)
        with self.assertRaisesRegex(ValueError, "reserved 2 KiB stack"):
            inspect_image.inspect(data)

    def test_generated_font_uses_existing_ascii_data(self):
        generated = generate_font.generate()
        self.assertIn("ts21_font[59][24]", generated)
        self.assertEqual(generated.count("  {"), 59)
        self.assertTrue(generated.isascii())


if __name__ == "__main__":
    unittest.main()
