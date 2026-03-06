import os
import tempfile
import unittest

from portfolio.industry import load_industry_map


class IndustryMapTestCase(unittest.TestCase):
    def test_load_industry_map(self) -> None:
        content = "symbol,industry\n600519,食品饮料\n000001,银行\n300750,电池\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "industry.csv")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            mapping = load_industry_map(path)
            self.assertEqual(mapping["600519"], "食品饮料")
            self.assertEqual(mapping["000001"], "银行")

    def test_load_industry_map_missing_columns(self) -> None:
        content = "code,name\n600519,贵州茅台\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "industry_bad.csv")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            with self.assertRaises(ValueError):
                load_industry_map(path)

    def test_load_industry_map_with_level(self) -> None:
        content = "symbol,industry_l1,industry_l2\n600519,消费,白酒\n000001,金融,银行\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "industry_level.csv")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            l1_map = load_industry_map(path, level="l1")
            l2_map = load_industry_map(path, level="l2")
            self.assertEqual(l1_map["600519"], "消费")
            self.assertEqual(l2_map["600519"], "白酒")

    def test_load_industry_map_invalid_level(self) -> None:
        content = "symbol,industry\n600519,食品饮料\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "industry_level_bad.csv")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            with self.assertRaises(ValueError):
                load_industry_map(path, level="l3")


if __name__ == "__main__":
    unittest.main()
