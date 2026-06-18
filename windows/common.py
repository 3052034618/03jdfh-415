import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import List, Optional, Dict, Callable
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTreeWidget,
    QTreeWidgetItem, QDialog, QComboBox, QSpinBox, QLineEdit, QTextEdit,
    QDialogButtonBox, QFormLayout, QListWidget, QListWidgetItem, QMessageBox,
    QTabWidget, QGroupBox, QScrollArea, QSizePolicy, QSplitter, QHeaderView,
    QFrame,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor, QBrush

from models import (
    Event, Ending, Condition, ConditionType, Choice, ChoiceEffect,
    ChoiceEffectType, GameState,
)


COLOR_BROKEN = QColor(255, 80, 80)
COLOR_VALID = QColor(80, 180, 80)
COLOR_WARN = QColor(230, 180, 60)
COLOR_INFO = QColor(80, 150, 230)
COLOR_DARK_BG = QColor(38, 38, 48)
COLOR_PANEL = QColor(48, 48, 58)
COLOR_BORDER = QColor(70, 70, 85)


def apply_dark_style(widget):
    widget.setStyleSheet(f"""
        QWidget {{
            background-color: {COLOR_DARK_BG.name()};
            color: #e0e0e0;
            font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
            font-size: 13px;
        }}
        QGroupBox {{
            border: 1px solid {COLOR_BORDER.name()};
            border-radius: 6px;
            margin-top: 14px;
            padding-top: 10px;
            background-color: {COLOR_PANEL.name()};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 6px;
            color: #9ecbff;
            font-weight: bold;
        }}
        QPushButton {{
            background-color: #4a6fa5;
            border: 1px solid #5a7fb5;
            border-radius: 4px;
            padding: 6px 14px;
            color: #fff;
        }}
        QPushButton:hover {{ background-color: #5a7fb5; }}
        QPushButton:pressed {{ background-color: #3a5f95; }}
        QPushButton:disabled {{ background-color: #555; color: #999; border-color: #666; }}
        QPushButton[danger="true"] {{ background-color: #a54a4a; border-color: #b55a5a; }}
        QPushButton[danger="true"]:hover {{ background-color: #b55a5a; }}
        QPushButton[success="true"] {{ background-color: #4a8a5a; border-color: #5a9a6a; }}
        QPushButton[success="true"]:hover {{ background-color: #5a9a6a; }}
        QLineEdit, QTextEdit, QComboBox, QSpinBox, QListWidget, QTreeWidget {{
            background-color: #2a2a35;
            border: 1px solid {COLOR_BORDER.name()};
            border-radius: 4px;
            padding: 4px;
            color: #e0e0e0;
            selection-background-color: #4a6fa5;
        }}
        QTabWidget::pane {{
            border: 1px solid {COLOR_BORDER.name()};
            border-radius: 4px;
            background-color: {COLOR_PANEL.name()};
        }}
        QTabBar::tab {{
            background-color: #383845;
            border: 1px solid {COLOR_BORDER.name()};
            border-bottom: none;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            padding: 8px 20px;
            margin-right: 2px;
            color: #aaa;
        }}
        QTabBar::tab:selected {{
            background-color: {COLOR_PANEL.name()};
            color: #9ecbff;
            font-weight: bold;
        }}
        QTabBar::tab:hover:!selected {{ background-color: #454555; }}
        QHeaderView::section {{
            background-color: #3a3a48;
            padding: 6px;
            border: none;
            border-right: 1px solid {COLOR_BORDER.name()};
            color: #9ecbff;
            font-weight: bold;
        }}
        QScrollBar:vertical, QScrollBar:horizontal {{
            background: #2a2a35;
            width: 10px;
            height: 10px;
            margin: 0;
        }}
        QScrollBar::handle {{
            background: #555;
            border-radius: 4px;
            min-height: 20px;
        }}
        QScrollBar::handle:hover {{ background: #666; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    """)


class ConditionEditDialog(QDialog):
    def __init__(self, condition: Optional[Condition] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑条件")
        self.setMinimumWidth(420)
        self._condition = condition or Condition(
            condition_type=ConditionType.HAS_CLUE, target=""
        )
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        layout = QFormLayout(self)
        self.cb_type = QComboBox()
        for ct in ConditionType:
            self.cb_type.addItem(str(ct), ct.value)
        self.cb_type.currentIndexChanged.connect(self._on_type_change)

        self.ed_target = QLineEdit()
        self.ed_target.setPlaceholderText("线索ID / 角色ID / 标记ID")

        self.sp_threshold = QSpinBox()
        self.sp_threshold.setRange(0, 100)
        self.sp_threshold.setValue(50)

        self.ed_desc = QLineEdit()
        self.ed_desc.setPlaceholderText("（可选）人类可读描述，留空自动生成")

        layout.addRow("条件类型：", self.cb_type)
        layout.addRow("目标（线索/角色/标记）：", self.ed_target)
        layout.addRow("阈值（仅恐惧值）：", self.sp_threshold)
        layout.addRow("自定义描述：", self.ed_desc)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)
        self._on_type_change()

    def _on_type_change(self):
        value = self.cb_type.currentData()
        needs_threshold = value in (ConditionType.FEAR_GTE.value, ConditionType.FEAR_LTE.value)
        self.sp_threshold.setEnabled(needs_threshold)
        needs_target = value not in (ConditionType.FEAR_GTE.value, ConditionType.FEAR_LTE.value)
        self.ed_target.setEnabled(needs_target)

    def _load_values(self):
        idx = self.cb_type.findData(self._condition.condition_type.value)
        if idx >= 0:
            self.cb_type.setCurrentIndex(idx)
        self.ed_target.setText(self._condition.target)
        if self._condition.threshold is not None:
            self.sp_threshold.setValue(self._condition.threshold)
        self.ed_desc.setText(self._condition.description)

    def get_condition(self) -> Condition:
        ct_val = self.cb_type.currentData()
        cond = Condition(
            condition_type=ConditionType.from_str(ct_val),
            target=self.ed_target.text().strip(),
            threshold=self.sp_threshold.value() if self.sp_threshold.isEnabled() else None,
            description=self.ed_desc.text().strip(),
        )
        if self._condition.id:
            cond.id = self._condition.id
        return cond


class EffectEditDialog(QDialog):
    def __init__(self, effect: Optional[ChoiceEffect] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑效果")
        self.setMinimumWidth(420)
        self._effect = effect or ChoiceEffect(
            effect_type=ChoiceEffectType.ADD_FEAR, target="", value=5
        )
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        layout = QFormLayout(self)
        self.cb_type = QComboBox()
        for et in ChoiceEffectType:
            self.cb_type.addItem(str(et), et.value)
        self.cb_type.currentIndexChanged.connect(self._on_type_change)

        self.ed_target = QLineEdit()
        self.ed_target.setPlaceholderText("线索ID / 角色ID / 标记ID")

        self.sp_value = QSpinBox()
        self.sp_value.setRange(-100, 100)
        self.sp_value.setValue(5)

        self.ed_desc = QLineEdit()
        self.ed_desc.setPlaceholderText("（可选）人类可读描述，留空自动生成")

        layout.addRow("效果类型：", self.cb_type)
        layout.addRow("目标（线索/角色/标记）：", self.ed_target)
        layout.addRow("数值（仅恐惧值）：", self.sp_value)
        layout.addRow("自定义描述：", self.ed_desc)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)
        self._on_type_change()

    def _on_type_change(self):
        value = self.cb_type.currentData()
        needs_value = (value == ChoiceEffectType.ADD_FEAR.value)
        self.sp_value.setEnabled(needs_value)
        needs_target = not needs_value
        self.ed_target.setEnabled(needs_target)

    def _load_values(self):
        idx = self.cb_type.findData(self._effect.effect_type.value)
        if idx >= 0:
            self.cb_type.setCurrentIndex(idx)
        self.ed_target.setText(self._effect.target)
        if self._effect.value is not None:
            self.sp_value.setValue(self._effect.value)
        self.ed_desc.setText(self._effect.description)

    def get_effect(self) -> ChoiceEffect:
        et_val = self.cb_type.currentData()
        eff = ChoiceEffect(
            effect_type=ChoiceEffectType.from_str(et_val),
            target=self.ed_target.text().strip(),
            value=self.sp_value.value() if self.sp_value.isEnabled() else None,
            description=self.ed_desc.text().strip(),
        )
        if self._effect.id:
            eff.id = self._effect.id
        return eff
