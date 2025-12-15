"""
MoneyDog 终端应用入口
提供交互式配置界面，用户可以在运行前配置参数
"""
import configparser
import os
import sys
from tabulate import tabulate
from main import load_strategy
from utils.logger import info, error


class ConfigApp:
    """
    配置应用类
    提供交互式配置界面和程序运行功能
    """
    
    def __init__(self, config_file: str = "config.ini"):
        """
        初始化配置应用
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self.load_config()
    
    def load_config(self):
        """
        加载配置文件
        """
        if os.path.exists(self.config_file):
            self.config.read(self.config_file, encoding='utf-8')
        else:
            print(f"警告: 配置文件 {self.config_file} 不存在，将使用默认配置")
    
    def save_config(self):
        """
        保存配置到文件
        
        Returns:
            bool: 保存是否成功
        """
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                self.config.write(f)
            return True
        except Exception as e:
            print(f"保存配置失败: {e}")
            return False
    
    def show_config(self):
        """
        显示当前所有配置
        """
        print("\n" + "="*60)
        print("当前配置信息")
        print("="*60)
        
        for section in self.config.sections():
            print(f"\n[{section}]")
            items = []
            for key, value in self.config.items(section):
                # 隐藏注释行
                if not key.startswith('#'):
                    items.append([key, value])
            if items:
                print(tabulate(items, headers=["配置项", "值"], tablefmt="grid"))
    
    def show_section_config(self, section: str):
        """
        显示指定配置段的配置
        
        Args:
            section: 配置段名称
        """
        if not self.config.has_section(section):
            print(f"配置段 [{section}] 不存在")
            return
        
        print(f"\n[{section}]")
        items = []
        for key, value in self.config.items(section):
            if not key.startswith('#'):
                items.append([key, value])
        if items:
            print(tabulate(items, headers=["配置项", "值"], tablefmt="grid"))
    
    def edit_config(self):
        """
        交互式编辑配置
        """
        sections = {
            '1': ('LOGGING', '日志配置'),
            '2': ('DATA', '数据配置'),
            '3': ('STRATEGY', '策略配置'),
            '4': ('BACKTEST', '回测配置'),
        }
        
        print("\n" + "="*60)
        print("配置编辑")
        print("="*60)
        print("\n请选择要编辑的配置段:")
        for key, (section, desc) in sections.items():
            print(f"  {key}. {desc} [{section}]")
        print("  0. 返回主菜单")
        
        choice = input("\n请输入选项 (0-4): ").strip()
        
        if choice == '0':
            return
        
        if choice not in sections:
            print("无效选项")
            return
        
        section, desc = sections[choice]
        self.edit_section(section, desc)
    
    def edit_section(self, section: str, section_desc: str):
        """
        编辑指定配置段
        
        Args:
            section: 配置段名称
            section_desc: 配置段描述
        """
        if not self.config.has_section(section):
            self.config.add_section(section)
        
        while True:
            print(f"\n编辑配置段: {section_desc} [{section}]")
            print("-" * 60)
            
            # 显示当前配置
            self.show_section_config(section)
            
            # 获取该段的所有配置项
            items = []
            for key, value in self.config.items(section):
                if not key.startswith('#'):
                    items.append((key, value))
            
            if not items:
                print("该配置段暂无配置项")
                return
            
            print("\n请选择要修改的配置项:")
            for idx, (key, value) in enumerate(items, 1):
                print(f"  {idx}. {key} = {value}")
            print("  0. 返回")
            
            try:
                choice = input("\n请输入选项: ").strip()
                if choice == '0':
                    break
                
                idx = int(choice) - 1
                if 0 <= idx < len(items):
                    key, old_value = items[idx]
                    new_value = input(f"\n请输入新值 (当前值: {old_value}, 直接回车保持原值): ").strip()
                    
                    if new_value:
                        self.config.set(section, key, new_value)
                        if self.save_config():
                            print(f"✓ 配置已更新: {key} = {new_value}")
                        else:
                            print("✗ 配置更新失败")
                    else:
                        print("配置未更改")
                    
                    # 询问是否继续编辑
                    continue_edit = input("\n是否继续编辑此配置段? (y/n): ").strip().lower()
                    if continue_edit != 'y':
                        break
                else:
                    print("无效选项，请重新选择")
            except ValueError:
                print("请输入有效的数字")
            except Exception as e:
                print(f"编辑配置时出错: {e}")
    
    def run_strategy(self):
        """
        运行策略程序
        """
        print("\n" + "="*60)
        print("运行策略")
        print("="*60)
        
        # 显示当前配置摘要
        print("\n当前运行配置:")
        try:
            strategy_module = self.config.get('STRATEGY', 'strategy_module', fallback='N/A')
            strategy_class = self.config.get('STRATEGY', 'strategy_class', fallback='N/A')
            backtest_start = self.config.get('BACKTEST', 'backtest_start_time', fallback='N/A')
            backtest_end = self.config.get('BACKTEST', 'backtest_end_time', fallback='N/A')
            
            summary = [
                ["策略模块", strategy_module],
                ["策略类", strategy_class],
                ["回测开始时间", backtest_start],
                ["回测结束时间", backtest_end],
            ]
            print(tabulate(summary, headers=["配置项", "值"], tablefmt="grid"))
        except Exception as e:
            print(f"读取配置摘要失败: {e}")
        
        confirm = input("\n确认运行? (y/n): ").strip().lower()
        if confirm != 'y':
            print("已取消运行")
            return
        
        print("\n开始运行策略...")
        print("-" * 60)
        
        try:
            strategy = load_strategy()
            strategy.run()
            print("\n" + "-" * 60)
            print("策略运行完成")
        except Exception as e:
            error(f"策略运行失败: {e}")
            print(f"\n错误: {e}")
    
    def show_menu(self):
        """
        显示主菜单
        """
        print("\n" + "="*60)
        print("MoneyDog 量化交易系统")
        print("="*60)
        print("\n主菜单:")
        print("  1. 查看当前配置")
        print("  2. 编辑配置")
        print("  3. 运行策略")
        print("  0. 退出")
    
    def run(self):
        """
        运行应用主循环
        """
        while True:
            self.show_menu()
            choice = input("\n请输入选项 (0-3): ").strip()
            
            if choice == '0':
                print("\n感谢使用 MoneyDog，再见！")
                break
            elif choice == '1':
                self.show_config()
                input("\n按回车键返回主菜单...")
            elif choice == '2':
                self.edit_config()
            elif choice == '3':
                self.run_strategy()
                input("\n按回车键返回主菜单...")
            else:
                print("无效选项，请重新选择")


def main():
    """
    主函数入口
    """
    try:
        app = ConfigApp()
        app.run()
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
        sys.exit(0)
    except Exception as e:
        error(f"程序运行出错: {e}")
        print(f"\n错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
