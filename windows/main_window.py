import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import List, Optional
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QMessageBox, QFileDialog, QStatusBar, QApplication,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QAction, QKeySequence

from models import Event, Ending, GameState
from services.storage import ScriptStorage
from services.validator import CausalityValidator
from services.sample_data import create_sample_data
from .common import apply_dark_style
from .event_input import EventInputPanel
from .deduction import EndingDeductionPanel
from .contradiction import ContradictionPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("因果链校验器 · 恐怖剧本定稿工具")
        self.setMinimumSize(1200, 780)
        apply_dark_style(self)

        self._events: List[Event] = []
        self._endings: List[Ending] = []
        self._initial_state = GameState()
        self._metadata = {"title": "未命名恐怖剧本", "version": 1}
        self._storage = ScriptStorage()

        self._build_ui()
        self._build_menu()
        self._load_or_init_data()

    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(56)
        header.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #1a1a25, stop:1 #2a2040);"
            "border-bottom: 1px solid #4a3a6a;"
        )
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)
        hl.setSpacing(14)

        title_lbl = QLabel("🧟 因果链校验器")
        title_lbl.setFont(QFont("Microsoft YaHei", 15, QFont.Bold))
        title_lbl.setStyleSheet("color: #c9b3ff; letter-spacing: 1px;")
        hl.addWidget(title_lbl)

        sub = QLabel("面向独立恐怖游戏编剧 · 多结局逻辑一致性检查工具")
        sub.setStyleSheet("color: #999; font-size: 12px;")
        hl.addWidget(sub)
        hl.addStretch()

        for txt, tip, slot, prop in [
            ("💾 保存", "保存剧本到本地 (Ctrl+S)", self._on_save, ""),
            ("📂 导入", "从 JSON 文件导入剧本", self._on_import, ""),
            ("📤 导出", "导出为 JSON 文件", self._on_export, ""),
            ("🎮 加载示例", "加载「疗养院」示例剧本", self._on_load_sample, "success"),
        ]:
            btn = QPushButton(txt)
            if prop:
                btn.setProperty(prop, True)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            hl.addWidget(btn)

        root.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        self.panel_event = EventInputPanel(self._events, self._endings)
        self.panel_deduction = EndingDeductionPanel(self._events, self._endings)
        self.panel_contradiction = ContradictionPanel(self._events, self._endings)

        self.tabs.addTab(self.panel_event, "📝 事件录入")
        self.tabs.addTab(self.panel_deduction, "🔍 结局推演")
        self.tabs.addTab(self.panel_contradiction, "⚠ 矛盾提示")
        root.addWidget(self.tabs, 1)

        self.setCentralWidget(central)

        self.status = QStatusBar()
        self.status.setStyleSheet("background: #1e1e28; color: #999; border-top: 1px solid #333;")
        self.setStatusBar(self.status)
        self._update_status("就绪")

        self.panel_event.data_changed.connect(self._on_data_changed)
        self.panel_deduction.data_changed.connect(self._on_data_changed)
        self.panel_deduction.navigate_event_requested.connect(self._navigate_to_event)
        self.panel_contradiction.navigate_event_requested.connect(self._navigate_to_event)
        self.panel_contradiction.navigate_ending_requested.connect(self._navigate_to_ending)

    def _build_menu(self):
        mb = self.menuBar()
        mb.setStyleSheet("""
            QMenuBar { background: #24242f; color: #ccc; border-bottom: 1px solid #333; padding: 2px; }
            QMenuBar::item:selected { background: #3a3a4e; color: #fff; }
            QMenu { background: #2a2a38; color: #ccc; border: 1px solid #444; }
            QMenu::item:selected { background: #4a6fa5; }
        """)
        m_file = mb.addMenu("文件(&F)")
        act_save = QAction("保存", self)
        act_save.setShortcut(QKeySequence.Save)
        act_save.triggered.connect(self._on_save)
        m_file.addAction(act_save)

        act_import = QAction("导入剧本...", self)
        act_import.triggered.connect(self._on_import)
        m_file.addAction(act_import)

        act_export = QAction("导出剧本...", self)
        act_export.triggered.connect(self._on_export)
        m_file.addAction(act_export)

        m_file.addSeparator()
        act_sample = QAction("加载示例剧本", self)
        act_sample.triggered.connect(self._on_load_sample)
        m_file.addAction(act_sample)

        m_file.addSeparator()
        act_quit = QAction("退出", self)
        act_quit.setShortcut(QKeySequence.Quit)
        act_quit.triggered.connect(self.close)
        m_file.addAction(act_quit)

        m_view = mb.addMenu("视图(&V)")
        for i, name in enumerate(["事件录入", "结局推演", "矛盾提示"]):
            act = QAction(f"跳转到「{name}」", self)
            act.setShortcut(QKeySequence(f"Ctrl+{i+1}"))
            act.triggered.connect(lambda _=False, idx=i: self.tabs.setCurrentIndex(idx))
            m_view.addAction(act)

        m_help = mb.addMenu("帮助(&H)")
        act_about = QAction("关于", self)
        act_about.triggered.connect(self._on_about)
        m_help.addAction(act_about)

    def _load_or_init_data(self):
        loaded = self._storage.load()
        if loaded:
            self._events, self._endings, self._initial_state, self._metadata = loaded
            self._sync_panels()
            self._update_status(f"已加载剧本：{self._metadata.get('title', '')}")
        else:
            self._on_load_sample(silent=True)

    def _on_data_changed(self):
        self._dirty = True
        self._update_status("已修改 · 记得保存")

    def _sync_panels(self):
        self.panel_event.set_data(self._events, self._endings)
        self.panel_deduction.set_data(self._events, self._endings)
        self.panel_contradiction.set_data(self._events, self._endings)

    def _on_save(self):
        ok = self._storage.save(self._events, self._endings, self._initial_state, self._metadata)
        if ok:
            self._update_status(f"✅ 已保存到 {self._storage.file_path}")
            self._dirty = False
        else:
            QMessageBox.critical(self, "保存失败", "保存文件时出错，请检查路径权限。")

    def _on_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择剧本 JSON 文件", "", "JSON 文件 (*.json)"
        )
        if not path:
            return
        data = self._storage.import_from(path)
        if data:
            self._events, self._endings, self._initial_state, self._metadata = data
            self._sync_panels()
            self._update_status(f"✅ 已导入：{self._metadata.get('title', '')}")
        else:
            QMessageBox.warning(self, "导入失败", "无法解析该文件。")

    def _on_export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出剧本", self._metadata.get("title", "script") + ".json",
            "JSON 文件 (*.json)"
        )
        if not path:
            return
        ok = self._storage.export_to(path, self._events, self._endings, self._initial_state, self._metadata)
        if ok:
            self._update_status(f"✅ 已导出到 {path}")
        else:
            QMessageBox.critical(self, "导出失败", "写入文件时出错。")

    def _on_load_sample(self, silent: bool = False):
        self._events, self._endings, self._initial_state = create_sample_data()
        self._metadata = {"title": "示例：迷雾疗养院", "version": 1}
        self._sync_panels()
        msg = "✅ 已加载示例剧本「迷雾疗养院」，共 {0} 章 / {1} 个事件 / {2} 个结局".format(
            len({e.chapter for e in self._events}),
            len(self._events),
            len(self._endings),
        )
        self._update_status(msg)
        if not silent:
            QMessageBox.information(self, "示例已加载", msg + "\n\n可在「结局推演」中挑选结局开始校验，或在「矛盾提示」中一键全局检查。")

    def _on_about(self):
        QMessageBox.information(
            self, "关于 因果链校验器",
            "因果链校验器 v1.0\n\n"
            "面向独立恐怖游戏编剧的桌面端多结局逻辑一致性检查工具。\n\n"
            "📝 事件录入 — 按章节录入关键事件和选择的影响\n"
            "🔍 结局推演 — 回放导致指定结局的必要条件路径\n"
            "⚠ 矛盾提示 — 标出缺失条件与线索/台词矛盾\n\n"
            "不替作者写剧情，只帮把鬼怪规则、人物动机、玩家选择的因果捋顺。"
        )

    def _update_status(self, msg: str):
        self.status.showMessage(f"  {msg}")

    def _navigate_to_event(self, event_id: str):
        self.tabs.setCurrentIndex(0)
        tree = self.panel_event.tree_events
        for i in range(tree.topLevelItemCount()):
            ch_item = tree.topLevelItem(i)
            for j in range(ch_item.childCount()):
                child = ch_item.child(j)
                if child.data(0, Qt.UserRole) == event_id:
                    tree.setCurrentItem(child)
                    tree.scrollToItem(child)
                    self._update_status(f"已定位到事件")
                    return
        ev = next((e for e in self._events if e.id == event_id), None)
        if ev:
            self._update_status(f"事件「{ev.title}」在列表中，但未被选中，请手动查找")

    def _navigate_to_ending(self, ending_id: str):
        self.tabs.setCurrentIndex(1)
        for i, end in enumerate(self._endings):
            if end.id == ending_id:
                self.panel_deduction.lst_endings.setCurrentRow(i)
                self._update_status("已定位到结局")
                return
