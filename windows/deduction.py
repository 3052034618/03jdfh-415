import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import List, Optional, Dict
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTreeWidget,
    QTreeWidgetItem, QComboBox, QLineEdit, QTextEdit,
    QFormLayout, QListWidget, QListWidgetItem, QMessageBox,
    QGroupBox, QScrollArea, QSplitter, QFrame, QTabWidget,
    QProgressBar, QSizePolicy, QDialog, QDialogButtonBox, QHeaderView,
    QTableWidget, QTableWidgetItem, QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor, QBrush

from models import (
    Event, Ending, Condition, ConditionType, Choice, ChoiceEffect,
    ChoiceEffectType, GameState, CharacterStatus,
)
from services.validator import (
    CausalityValidator, ValidationResult, TimelineStep,
    LinkStatus, Contradiction, BranchPreview,
)
from .common import (
    apply_dark_style, ConditionEditDialog, EffectEditDialog,
    COLOR_BROKEN, COLOR_VALID, COLOR_WARN, COLOR_INFO,
)


class BranchCompareDialog(QDialog):
    def __init__(self, step: TimelineStep, endings: List[Ending], parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔀 分支走向对比")
        self.setMinimumSize(800, 560)
        self._step = step
        self._endings = endings
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        event = self._step.event
        header = QLabel("📌 第{0}章「{1}」— 选择分支对比".format(event.chapter, event.title))
        header.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        header.setStyleSheet("color: #9ecbff; padding: 6px;")
        layout.addWidget(header)

        sel_row = QHBoxLayout()
        sel_row.addWidget(QLabel("左侧选择："))
        self.cmb_left = QComboBox()
        sel_row.addWidget(self.cmb_left, 1)
        sel_row.addWidget(QLabel("右侧选择："))
        self.cmb_right = QComboBox()
        sel_row.addWidget(self.cmb_right, 1)
        self.btn_compare = QPushButton("📊 开始对比")
        self.btn_compare.setProperty("success", True)
        self.btn_compare.clicked.connect(self._do_compare)
        sel_row.addWidget(self.btn_compare)
        layout.addLayout(sel_row)

        previews = self._step.all_branch_previews
        for bp in previews:
            label = "{0} (评分:{1})".format(bp.choice.text or "(未命名)", 0)
            self.cmb_left.addItem(label, bp.choice.id)
            self.cmb_right.addItem(label, bp.choice.id)
        if previews:
            self.cmb_left.setCurrentIndex(0)
            self.cmb_right.setCurrentIndex(min(1, len(previews) - 1))

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["对比维度", "左侧选择", "右侧选择"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _do_compare(self):
        left_id = self.cmb_left.currentData()
        right_id = self.cmb_right.currentData()
        if not left_id or not right_id:
            return

        left_bp = next((bp for bp in self._step.all_branch_previews if bp.choice.id == left_id), None)
        right_bp = next((bp for bp in self._step.all_branch_previews if bp.choice.id == right_id), None)
        if not left_bp or not right_bp:
            return

        rows = []

        left_text = left_bp.choice.text or "(未命名)"
        right_text = right_bp.choice.text or "(未命名)"
        rows.append(("选择", left_text, right_text))

        left_fear = "恐惧值: {0} ({1}{2})".format(
            left_bp.state_after.fear_level,
            "+" if left_bp.fear_diff >= 0 else "",
            left_bp.fear_diff,
        )
        right_fear = "恐惧值: {0} ({1}{2})".format(
            right_bp.state_after.fear_level,
            "+" if right_bp.fear_diff >= 0 else "",
            right_bp.fear_diff,
        )
        rows.append(("恐惧值变化", left_fear, right_fear))

        left_clues = "获得: {0}".format(", ".join(left_bp.clues_added) if left_bp.clues_added else "无")
        right_clues = "获得: {0}".format(", ".join(right_bp.clues_added) if right_bp.clues_added else "无")
        rows.append(("线索获得", left_clues, right_clues))

        if left_bp.clues_removed or right_bp.clues_removed:
            left_lost = "失去: {0}".format(", ".join(left_bp.clues_removed) if left_bp.clues_removed else "无")
            right_lost = "失去: {0}".format(", ".join(right_bp.clues_removed) if right_bp.clues_removed else "无")
            rows.append(("线索失去", left_lost, right_lost))

        left_chars = "无变化"
        if left_bp.chars_changed:
            parts = []
            for cid, (old, new) in left_bp.chars_changed.items():
                parts.append("{0}: {1}→{2}".format(cid, str(old), str(new)))
            left_chars = "; ".join(parts)
        right_chars = "无变化"
        if right_bp.chars_changed:
            parts = []
            for cid, (old, new) in right_bp.chars_changed.items():
                parts.append("{0}: {1}→{2}".format(cid, str(old), str(new)))
            right_chars = "; ".join(parts)
        rows.append(("角色状态变化", left_chars, right_chars))

        left_flags = "设置: {0}".format(", ".join(left_bp.flags_set[:5]) if left_bp.flags_set else "无")
        right_flags = "设置: {0}".format(", ".join(right_bp.flags_set[:5]) if right_bp.flags_set else "无")
        rows.append(("标记变化", left_flags, right_flags))

        for ending in self._endings:
            left_met = left_bp.ending_closeness.get(ending.id, 0)
            right_met = right_bp.ending_closeness.get(ending.id, 0)
            total = len(ending.conditions)
            left_str = "{0}/{1}".format(left_met, total)
            right_str = "{0}/{1}".format(right_met, total)
            rows.append(("→ " + ending.title, left_str, right_str))

        self.table.setRowCount(len(rows))
        for r, (dim, left_val, right_val) in enumerate(rows):
            dim_item = QTableWidgetItem(dim)
            dim_item.setForeground(QBrush(COLOR_INFO))
            left_item = QTableWidgetItem(left_val)
            right_item = QTableWidgetItem(right_val)
            if r > 0 and left_val != right_val:
                left_item.setForeground(QBrush(COLOR_WARN))
                right_item.setForeground(QBrush(COLOR_WARN))
            self.table.setItem(r, 0, dim_item)
            self.table.setItem(r, 1, left_item)
            self.table.setItem(r, 2, right_item)


class EndingEditDialog(QDialog):
    def __init__(self, ending: Optional[Ending] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑结局")
        self.setMinimumWidth(520)
        self.setMinimumHeight(480)
        self._ending = ending or Ending(title="新结局")
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.ed_title = QLineEdit()
        self.ed_desc = QTextEdit()
        self.ed_desc.setFixedHeight(80)
        form.addRow("结局名称：", self.ed_title)
        form.addRow("结局描述：", self.ed_desc)
        layout.addLayout(form)

        gb = QGroupBox("🎯 必要条件（全部满足才能触发此结局）")
        v = QVBoxLayout(gb)
        self.lst_conds = QListWidget()
        self.lst_conds.itemDoubleClicked.connect(self._edit_cond)
        v.addWidget(self.lst_conds)
        bar = QHBoxLayout()
        btn_a = QPushButton("+ 新增条件")
        btn_a.clicked.connect(self._add_cond)
        btn_e = QPushButton("编辑选中")
        btn_e.clicked.connect(self._edit_cond)
        btn_d = QPushButton("删除选中")
        btn_d.setProperty("danger", True)
        btn_d.clicked.connect(self._del_cond)
        bar.addWidget(btn_a)
        bar.addWidget(btn_e)
        bar.addWidget(btn_d)
        v.addLayout(bar)
        layout.addWidget(gb, 1)

        gb2 = QGroupBox("💬 关键台词/剧情提示（每行一条，用于矛盾检测）")
        v2 = QVBoxLayout(gb2)
        self.ed_dialogues = QTextEdit()
        self.ed_dialogues.setPlaceholderText("例：\n玩家：这张祭坛的照片我好像在哪里见过...\n护士：你果然打开了地下室")
        v2.addWidget(self.ed_dialogues)
        layout.addWidget(gb2, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _load_values(self):
        self.ed_title.setText(self._ending.title)
        self.ed_desc.setPlainText(self._ending.description)
        self.lst_conds.clear()
        for c in self._ending.conditions:
            item = QListWidgetItem(c.human_readable())
            item.setData(Qt.UserRole, c.id)
            item.setForeground(QBrush(COLOR_VALID))
            self.lst_conds.addItem(item)
        self.ed_dialogues.setPlainText("\n".join(self._ending.dialogue_hints))

    def _add_cond(self):
        dlg = ConditionEditDialog(parent=self)
        if dlg.exec() == dlg.Accepted:
            self._ending.conditions.append(dlg.get_condition())
            self._load_values()

    def _edit_cond(self):
        row = self.lst_conds.currentRow()
        if row < 0 or row >= len(self._ending.conditions):
            return
        dlg = ConditionEditDialog(self._ending.conditions[row], self)
        if dlg.exec() == dlg.Accepted:
            self._ending.conditions[row] = dlg.get_condition()
            self._load_values()

    def _del_cond(self):
        row = self.lst_conds.currentRow()
        if row < 0 or row >= len(self._ending.conditions):
            return
        del self._ending.conditions[row]
        self._load_values()

    def get_ending(self) -> Ending:
        hints = [h.strip() for h in self.ed_dialogues.toPlainText().split("\n") if h.strip()]
        end = Ending(
            title=self.ed_title.text().strip() or "(未命名结局)",
            description=self.ed_desc.toPlainText().strip(),
            conditions=list(self._ending.conditions),
            dialogue_hints=hints,
        )
        if self._ending.id:
            end.id = self._ending.id
        return end


class EndingDeductionPanel(QWidget):
    navigate_event_requested = Signal(str)
    navigate_ending_requested = Signal(str)
    data_changed = Signal()

    def __init__(self, events: List[Event], endings: List[Ending], initial_state: Optional[GameState] = None, parent=None):
        super().__init__(parent)
        self._events = events
        self._endings = endings
        self._initial_state = initial_state or GameState()
        self._current_result: Optional[ValidationResult] = None
        self._current_ending: Optional[Ending] = None
        self._build_ui()
        self._refresh_endings()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        left = QFrame()
        left.setFixedWidth(340)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(6)

        head = QLabel("🎬 结局列表")
        head.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        head.setStyleSheet("color: #9ecbff; padding: 4px;")
        lv.addWidget(head)

        self.lst_endings = QListWidget()
        self.lst_endings.currentRowChanged.connect(self._on_select_ending)
        lv.addWidget(self.lst_endings, 1)

        b = QHBoxLayout()
        ba = QPushButton("+ 新增结局")
        ba.clicked.connect(self._add_ending)
        be = QPushButton("编辑")
        be.clicked.connect(self._edit_ending)
        bd = QPushButton("删除")
        bd.setProperty("danger", True)
        bd.clicked.connect(self._del_ending)
        b.addWidget(ba)
        b.addWidget(be)
        b.addWidget(bd)
        lv.addLayout(b)

        self.lbl_ending_desc = QLabel("(选择结局后查看详情)")
        self.lbl_ending_desc.setWordWrap(True)
        self.lbl_ending_desc.setStyleSheet(
            "background: #2a2a35; border: 1px solid #44445a; border-radius: 4px;"
            "padding: 8px; color: #ccc;"
        )
        lv.addWidget(self.lbl_ending_desc)

        right = QFrame()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(6)

        top = QFrame()
        th = QHBoxLayout(top)
        th.setContentsMargins(0, 0, 0, 0)
        title = QLabel("🔍 时间线推演回放")
        title.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        title.setStyleSheet("color: #9ecbff; padding: 4px;")
        th.addWidget(title)
        th.addStretch()

        self.btn_run = QPushButton("▶ 开始校验")
        self.btn_run.setProperty("success", True)
        self.btn_run.clicked.connect(self._run_validation)
        th.addWidget(self.btn_run)

        self.lbl_status = QLabel("等待校验...")
        self.lbl_status.setFont(QFont("Microsoft YaHei", 9))
        self.lbl_status.setStyleSheet("padding: 4px 10px; border-radius: 4px;")
        th.addWidget(self.lbl_status)

        rv.addWidget(top)

        self.lbl_initial_state = QLabel("📌 开局初始：")
        self.lbl_initial_state.setStyleSheet(
            "background: #2a2a35; border: 1px solid #44445a; border-radius: 4px;"
            "padding: 6px 10px; color: #c9b3ff; font-weight: bold;"
        )
        rv.addWidget(self.lbl_initial_state)
        self._update_initial_state_label()

        self.tree_timeline = QTreeWidget()
        self.tree_timeline.setHeaderLabels(["章节/事件", "状态", "玩家选择 / 影响", "恐惧值 / 关键条件"])
        self.tree_timeline.header().setStretchLastSection(False)
        self.tree_timeline.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree_timeline.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree_timeline.header().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tree_timeline.header().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tree_timeline.itemDoubleClicked.connect(self._on_timeline_double_click)
        rv.addWidget(self.tree_timeline, 1)

        gb = QGroupBox("🏁 结局条件达成情况")
        gv = QVBoxLayout(gb)
        self.lbl_summary = QLabel("")
        self.lbl_summary.setWordWrap(True)
        self.lbl_summary.setStyleSheet("color: #ddd; padding: 4px;")
        gv.addWidget(self.lbl_summary)

        row = QHBoxLayout()
        col1 = QVBoxLayout()
        col1.addWidget(QLabel("✅ 已满足："))
        self.lst_met = QListWidget()
        self.lst_met.setFixedHeight(140)
        self.lst_met.itemDoubleClicked.connect(self._on_met_double_click)
        col1.addWidget(self.lst_met)
        row.addLayout(col1, 1)

        col2 = QVBoxLayout()
        col2.addWidget(QLabel("❌ 未满足（断链）："))
        self.lst_missing = QListWidget()
        self.lst_missing.setFixedHeight(140)
        self.lst_missing.itemDoubleClicked.connect(self._on_missing_double_click)
        col2.addWidget(self.lst_missing)
        row.addLayout(col2, 1)
        gv.addLayout(row)
        rv.addWidget(gb)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter)

    def set_data(self, events: List[Event], endings: List[Ending], initial_state: Optional[GameState] = None):
        self._events = events
        self._endings = endings
        if initial_state is not None:
            self._initial_state = initial_state
        self._current_result = None
        self._current_ending = None
        self._refresh_endings()
        self.tree_timeline.clear()
        self.lst_met.clear()
        self.lst_missing.clear()
        self.lbl_summary.setText("")
        self._set_status("等待校验...", COLOR_INFO)
        self._update_initial_state_label()

    def _update_initial_state_label(self):
        st = self._initial_state
        parts = ["恐惧值:{0}".format(st.fear_level)]
        flags_on = [k for k, v in st.flags.items() if v]
        if flags_on:
            parts.append("标记:{0}个".format(len(flags_on)))
        clues_on = [k for k, v in st.clues.items() if v]
        if clues_on:
            parts.append("线索:{0}个".format(len(clues_on)))
        chars = ["{0}={1}".format(k, str(v)) for k, v in st.characters.items()]
        if chars:
            parts.append("角色:{0}个".format(len(chars)))
        self.lbl_initial_state.setText("📌 开局初始：" + " ｜ ".join(parts))

    def get_endings(self) -> List[Ending]:
        return self._endings

    def get_last_result(self) -> Optional[ValidationResult]:
        return self._current_result

    def get_current_ending(self) -> Optional[Ending]:
        return self._current_ending

    def _refresh_endings(self):
        self.lst_endings.clear()
        for e in self._endings:
            item = QListWidgetItem("🎬 {0}".format(e.title or "(未命名)"))
            item.setData(Qt.UserRole, e.id)
            self.lst_endings.addItem(item)
        if self._endings:
            self.lst_endings.setCurrentRow(0)
        else:
            self.lbl_ending_desc.setText("(暂无结局，请先添加)")

    def _on_select_ending(self, row: int):
        if row < 0 or row >= len(self._endings):
            self._current_ending = None
            self.lbl_ending_desc.setText("(选择结局后查看详情)")
            return
        end = self._endings[row]
        self._current_ending = end
        text = "【{0}】\n{1}\n\n必要条件：{2} 条\n关键台词：{3} 条".format(
            end.title, end.description or "(无描述)", len(end.conditions), len(end.dialogue_hints)
        )
        self.lbl_ending_desc.setText(text)

    def _add_ending(self):
        dlg = EndingEditDialog(parent=self)
        if dlg.exec() == dlg.Accepted:
            self._endings.append(dlg.get_ending())
            self._refresh_endings()
            self.data_changed.emit()

    def _edit_ending(self):
        row = self.lst_endings.currentRow()
        if row < 0 or row >= len(self._endings):
            return
        dlg = EndingEditDialog(self._endings[row], self)
        if dlg.exec() == dlg.Accepted:
            self._endings[row] = dlg.get_ending()
            self._refresh_endings()
            self.lst_endings.setCurrentRow(row)
            self.data_changed.emit()

    def _del_ending(self):
        row = self.lst_endings.currentRow()
        if row < 0 or row >= len(self._endings):
            return
        end = self._endings[row]
        r = QMessageBox.question(
            self, "确认删除", "确定删除结局「{0}」吗？".format(end.title),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if r == QMessageBox.Yes:
            del self._endings[row]
            self._refresh_endings()
            self.data_changed.emit()

    def _run_validation(self):
        if not self._current_ending:
            QMessageBox.information(self, "提示", "请先选择一个结局。")
            return
        if not self._events:
            QMessageBox.warning(self, "警告", "当前没有任何事件，请先在「事件录入」中添加。")
            return
        validator = CausalityValidator(self._events, self._endings, self._initial_state)
        result = validator.simulate_path_to_ending(self._current_ending, self._initial_state)
        extra = validator.find_dialogue_contradictions(result, self._current_ending)
        result.contradictions.extend(extra)
        self._current_result = result
        self._render_result(result)

    def _set_status(self, text: str, color: QColor):
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet(
            "padding: 4px 10px; border-radius: 4px;"
            "background: {0}; color: white;".format(color.name())
        )

    def _render_result(self, result: ValidationResult):
        self.tree_timeline.clear()
        self.lst_met.clear()
        self.lst_missing.clear()

        if result.overall_status == LinkStatus.VALID:
            self._set_status("✅ 因果链完整", COLOR_VALID)
        elif result.overall_status == LinkStatus.WARN:
            self._set_status("⚠ 存在警告", COLOR_WARN)
        else:
            self._set_status("❌ 因果链断裂", COLOR_BROKEN)

        self.lbl_summary.setText(result.summary)

        for step in result.timeline:
            self._render_step(step)

        for c in result.ending_met_conditions:
            item = QListWidgetItem(c.human_readable())
            item.setForeground(QBrush(COLOR_VALID))
            self.lst_met.addItem(item)

        for c in result.ending_missing_conditions:
            item = QListWidgetItem(c.human_readable())
            item.setData(Qt.UserRole, ("ending_condition", c.id, self._current_ending.id if self._current_ending else None))
            item.setForeground(QBrush(COLOR_BROKEN))
            self.lst_missing.addItem(item)

        self.tree_timeline.expandAll()
        for i in range(4):
            self.tree_timeline.resizeColumnToContents(i)

    def _render_step(self, step: TimelineStep):
        ch_item = QTreeWidgetItem([
            "第 {0} 章".format(step.event.chapter), "", "", ""
        ])
        ch_item.setForeground(0, QBrush(COLOR_INFO))
        font = QFont()
        font.setBold(True)
        ch_item.setFont(0, font)
        self.tree_timeline.addTopLevelItem(ch_item)

        status_text = ""
        status_color = COLOR_VALID
        if step.event_condition_status == LinkStatus.SKIPPED:
            status_text = "🚫 未触发"
            status_color = COLOR_BROKEN
        elif step.event_condition_status == LinkStatus.BROKEN:
            status_text = "⛔ 跳过"
            status_color = COLOR_BROKEN
        elif step.event_condition_status == LinkStatus.WARN:
            status_text = "⚠ 非最优"
            status_color = COLOR_WARN
        else:
            status_text = "✔ 触发"
            status_color = COLOR_VALID

        title_note = ""
        if step.event_condition_status == LinkStatus.SKIPPED:
            title_note = "  （前置条件不满足，已跳过）"

        ev_item = QTreeWidgetItem([
            "  📌 {0}{1}".format(step.event.title, title_note),
            status_text,
            "",
            "恐惧值 {0} → {1}".format(step.state_before.fear_level, step.state_after.fear_level if step.state_after else "?"),
        ])
        ev_item.setData(0, Qt.UserRole, step.event.id)
        ev_item.setData(1, Qt.UserRole, step)
        ev_item.setForeground(1, QBrush(status_color))
        ev_item.setBackground(1, QBrush(status_color.lighter(250)))
        ev_item.setForeground(3, QBrush(COLOR_INFO))
        if step.event_condition_status == LinkStatus.SKIPPED:
            ev_item.setForeground(0, QBrush(COLOR_BROKEN))
            f = QFont(); f.setItalic(True); ev_item.setFont(0, f)
        ch_item.addChild(ev_item)

        if step.met_event_conditions:
            for cond in step.met_event_conditions:
                sub = QTreeWidgetItem([
                    "", "✓", "【满足前置】{0}".format(cond.human_readable()), ""
                ])
                sub.setForeground(1, QBrush(COLOR_VALID))
                sub.setForeground(2, QBrush(COLOR_VALID))
                sub.setData(0, Qt.UserRole, ("cond_met", step.event.id, cond.id))
                ev_item.addChild(sub)

        if step.broken_event_conditions:
            for cond in step.broken_event_conditions:
                sub = QTreeWidgetItem([
                    "", "⛔", "【缺失前置】{0}".format(cond.human_readable()), ""
                ])
                sub.setForeground(1, QBrush(COLOR_BROKEN))
                sub.setForeground(2, QBrush(COLOR_BROKEN))
                sub.setData(0, Qt.UserRole, ("cond_broken", step.event.id, cond.id))
                ev_item.addChild(sub)

        if step.all_choice_scores and step.event_condition_status != LinkStatus.SKIPPED:
            score_item = QTreeWidgetItem([
                "", "", "📊 选择评分预览（双击可打开分支对比）：", ""
            ])
            score_item.setForeground(2, QBrush(COLOR_WARN))
            f2 = QFont(); f2.setBold(True); score_item.setFont(2, f2)
            ev_item.addChild(score_item)

            best_score = max((s.score for s in step.all_choice_scores), default=0)
            for cs in step.all_choice_scores:
                is_best = cs.score == best_score and best_score > 0
                is_selected = (step.selected_choice and cs.choice.id == step.selected_choice.id)
                badge = ""
                if is_selected and is_best:
                    badge = "  🏆"
                elif is_selected:
                    badge = "  👤 (当前选择)"
                elif is_best:
                    badge = "  🎯 (最优)"

                met_str = "、".join(cs.met_conditions[:2]) if cs.met_conditions else ""
                prog_str = "、".join(cs.progress_conditions[:2]) if cs.progress_conditions else ""
                extra = []
                if met_str:
                    extra.append("✓ {0}".format(met_str))
                if prog_str:
                    extra.append("↗ {0}".format(prog_str))
                extra_str = "  [{0}]".format("; ".join(extra)) if extra else ""

                sub = QTreeWidgetItem([
                    "", "",
                    "  [{0:2d}分] {1}{2}{3}".format(cs.score, cs.choice.text or "(未命名)", badge, extra_str),
                    ""
                ])
                if is_selected:
                    sub.setBackground(2, QBrush(50, 60, 80))
                if is_best:
                    sub.setForeground(2, QBrush(COLOR_VALID))
                sub.setData(0, Qt.UserRole, ("choice", step.event.id, cs.choice.id))
                ev_item.addChild(sub)

            if step.all_branch_previews and len(step.all_branch_previews) >= 2:
                cmp_sub = QTreeWidgetItem([
                    "", "", "🔀 双击此处 → 打开分支对比对话框", ""
                ])
                cmp_sub.setForeground(2, QBrush(QColor(150, 200, 255)))
                cmp_sub.setData(0, Qt.UserRole, ("branch_compare", step.event.id, None))
                ev_item.addChild(cmp_sub)

        if step.selected_choice and step.event_condition_status != LinkStatus.SKIPPED:
            choice_text = step.selected_choice.text or "(未命名选项)"
            note = "  {0}".format(step.note) if step.note else ""
            ch_item2 = QTreeWidgetItem([
                "", "", "🔘 选择：{0}{1}".format(choice_text, note), ""
            ])
            ch_item2.setForeground(2, QBrush(COLOR_INFO))
            ev_item.addChild(ch_item2)
            for eff in step.choice_effects_applied:
                eff_text = eff.human_readable()
                sub = QTreeWidgetItem(["", "", "    → {0}".format(eff_text), ""])
                et = eff.effect_type
                if et == ChoiceEffectType.ADD_FEAR:
                    c = COLOR_BROKEN if (eff.value or 0) > 0 else COLOR_VALID
                elif et in (ChoiceEffectType.SET_CHAR_DEAD, ChoiceEffectType.SET_CHAR_MISSING, ChoiceEffectType.SET_CHAR_INSANE):
                    c = COLOR_BROKEN
                else:
                    c = COLOR_VALID
                sub.setForeground(2, QBrush(c))
                ev_item.addChild(sub)
        elif step.event_condition_status == LinkStatus.SKIPPED:
            sub = QTreeWidgetItem([
                "", "", "🔒 事件未触发，以上缺失条件满足后才可进入（双击跳转修改）", ""
            ])
            sub.setForeground(2, QBrush(COLOR_BROKEN))
            sub.setData(0, Qt.UserRole, ("skipped_hint", step.event.id, None))
            ev_item.addChild(sub)

        state_after = step.state_after or GameState()
        clues_active = [k for k, v in state_after.clues.items() if v]
        if clues_active:
            sub = QTreeWidgetItem([
                "", "", "💡 已掌握线索 ({0})：{1}{2}".format(
                    len(clues_active),
                    ", ".join(clues_active[:6]),
                    "..." if len(clues_active) > 6 else ""
                ), ""
            ])
            sub.setForeground(2, QBrush(COLOR_WARN))
            ev_item.addChild(sub)

        chars = {k: v for k, v in state_after.characters.items() if v.value != "alive"}
        if chars:
            labels = []
            for k, v in chars.items():
                labels.append("{0}→{1}".format(k, str(v)))
            sub = QTreeWidgetItem([
                "", "", "💀 角色状态：{0}".format(", ".join(labels)), ""
            ])
            sub.setForeground(2, QBrush(COLOR_BROKEN))
            ev_item.addChild(sub)

    def _on_timeline_double_click(self, item: QTreeWidgetItem, col: int):
        raw = item.data(0, Qt.UserRole)
        if raw is None:
            return

        if isinstance(raw, str):
            self.navigate_event_requested.emit(raw)
            return

        if isinstance(raw, tuple):
            tag = raw[0]
            if tag == "cond_broken":
                event_id = raw[1]
                self.navigate_event_requested.emit(event_id)
            elif tag == "cond_met":
                event_id = raw[1]
                self.navigate_event_requested.emit(event_id)
            elif tag == "choice":
                event_id = raw[1]
                self.navigate_event_requested.emit(event_id)
            elif tag == "branch_compare":
                step_data = item.parent().data(1, Qt.UserRole) if item.parent() else None
                if step_data and isinstance(step_data, TimelineStep):
                    if step_data.all_branch_previews and len(step_data.all_branch_previews) >= 2:
                        dlg = BranchCompareDialog(step_data, self._endings, self)
                        dlg.exec()
            elif tag == "skipped_hint":
                event_id = raw[1]
                self.navigate_event_requested.emit(event_id)

    def _on_met_double_click(self, item: QListWidgetItem):
        pass

    def _on_missing_double_click(self, item: QListWidgetItem):
        raw = item.data(Qt.UserRole)
        if raw and isinstance(raw, tuple) and len(raw) >= 3:
            tag, cond_id, ending_id = raw[0], raw[1], raw[2]
            if ending_id:
                self.navigate_ending_requested.emit(ending_id)
