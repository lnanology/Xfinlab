import json
import os
from typing import Dict


class ModuleManager:
    """
    Module Manager™ 用於管理功能模組的啟用狀態。
    """

    def __init__(self, flags_file="modules/feature_flags.json"):
        """
        初始化模組管理器。

        參數：
        flags_file (str): 功能標誌文件的相對路徑。
        """
        self.flags_file = flags_file
        self.feature_flags = self._load_flags()

    def _load_flags(self) -> Dict:
        """
        從 JSON 文件加載功能標誌。

        返回：
        dict: 功能標誌的鍵值對。
        """
        with open(self.flags_file, "r") as f:
            return json.load(f)

    def _save_flags(self):
        """
        將功能標誌保存到 JSON 文件。
        """
        with open(self.flags_file, "w") as f:
            json.dump(self.feature_flags, f, indent=2)

    def is_enabled(self, module_name: str) -> bool:
        """
        檢查指定模組是否啟用。

        參數：
        module_name (str): 模組名稱。

        返回：
        bool: 模組是否啟用。
        """
        return self.feature_flags.get(module_name, False)

    def enable_module(self, module_name: str):
        """
        啟用指定模組。

        參數：
        module_name (str): 模組名稱。
        """
        self.feature_flags[module_name] = True
        self._save_flags()

    def disable_module(self, module_name: str):
        """
        停用指定模組。

        參數：
        module_name (str): 模組名稱。
        """
        self.feature_flags[module_name] = False
        self._save_flags()


# 示例用法
if __name__ == "__main__":
    # 初始化模組管理器
    manager = ModuleManager()

    # 檢查模組狀態
    print("event_intelligence:", manager.is_enabled("event_intelligence"))  # True
    print("portfolio_research:", manager.is_enabled("portfolio_research"))  # False

    # 啟用模組
    manager.enable_module("portfolio_research")
    print(
        "portfolio_research 已啟用:", manager.is_enabled("portfolio_research")
    )  # True

    # 停用模組
    manager.disable_module("strategy_lab")
    print("strategy_lab 已停用:", manager.is_enabled("strategy_lab"))  # False
