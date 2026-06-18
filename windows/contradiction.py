import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import List, Optional, Dict, Set
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTreeWidget,
    QTreeWidgetItem, QComboBox, QLineEdit, QTextEdit, QCheckBox,
    QFormLayout, QListWidget, QListWidgetItem, QMessageBox,
    QGroupBox, QScrollArea, QSplitter, QFrame, QTabWidget,
    QProgressBar, QSizePolicy, QDialog, QDialogButtonBox, QHeaderView,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QFileDialog,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor, QBrush

from models import (
    Event, Ending, Condition, GameState, CharacterStatus,
)
from services.validator import (
    CausalityValidator, ValidationResult, LinkStatus, Contradiction,
    BranchPreview, FullBranchResult,
)
from .common import (
    apply_dark_style, COLOR_BROKEN, COLOR_VALID, COLOR_WARN, COLOR_INFO,
)


class ContradictionPanel(QWidget):
    navigate_event_requested = Signal(str)
    navigate_ending_requested = Signal(str)

    def __init__(self, events: List[Event], endings: List[Ending], initial_state: Optional[GameState] = None, parent=None):
        super().__init__(parent)
        self._events = events
        self._endings = endings
        self._initial_state = initial_state or GameState()
        self._results_cache: Dict[str, ValidationResult] = {}
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        top = QFrame()
        th = QHBoxLayout(top)
        th.setContentsMargins(0, 0, 0, 0)
        title = QLabel("⚠ 因果矛盾与审稿")
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        title.setStyleSheet("color: #9ecbff; padding: 4px;")
        th.addWidget(title)
        th.addStretch()

        self.chk_show_warnings = QCheckBox("包含警告级提示")
        self.chk_show_warnings.setChecked(True)
        self.chk_show_warnings.stateChanged.connect(self._refresh_list)
        th.addWidget(self.chk_show_warnings)

        self.btn_export = QPushButton("📤 导出审稿报告")
        self.btn_export.clicked.connect(self._export_report)
        self.btn_export.setEnabled(False)
        th.addWidget(self.btn_export)

        self.btn_check_all = QPushButton("🔎 全结局一键校验")
        self.btn_check_all.clicked.connect(self._check_all_endings)
        self.btn_check_all.setProperty("success", True)
        th.addWidget(self.btn_check_all)
        root.addWidget(top)

        self.tabs_view = QTabWidget()

        tab_issues = QWidget()
        ti_layout = QVBoxLayout(tab_issues)
        ti_layout.setContentsMargins(0, 0, 0, 0)

        body = QSplitter(Qt.Horizontal)

        left_frame = QFrame()
        lv = QVBoxLayout(left_frame)
        lv.setContentsMargins(0, 0, 0, 0)
        head_l = QLabel("🚩 矛盾列表（双击跳转定位）")
        head_l.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        head_l.setStyleSheet("color: #aaa; padding: 4px;")
        lv.addWidget(head_l)

        self.tree_issues = QTreeWidget()
        self.tree_issues.setHeaderLabels(["严重度", "分类", "概要"])
        self.tree_issues.header().setStretchLastSection(True)
        self.tree_issues.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree_issues.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree_issues.itemSelectionChanged.connect(self._on_select_issue)
        self.tree_issues.itemDoubleClicked.connect(self._on_double_click_issue)
        lv.addWidget(self.tree_issues, 1)

        self.lbl_stats = QLabel("尚未开始校验")
        self.lbl_stats.setStyleSheet("color: #999; padding: 4px;")
        lv.addWidget(self.lbl_stats)
        body.addWidget(left_frame)

        right_frame = QFrame()
        rv = QVBoxLayout(right_frame)
        rv.setContentsMargins(0, 0, 0, 0)
        head_r = QLabel("📋 详细说明 & 修改建议")
        head_r.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        head_r.setStyleSheet("color: #aaa; padding: 4px;")
        rv.addWidget(head_r)

        self.ed_detail = QTextEdit()
        self.ed_detail.setReadOnly(True)
        self.ed_detail.setStyleSheet("""
            QTextEdit {
                background-color: #2a2a35;
                border: 1px solid #44445a;
                border-radius: 4px;
                padding: 10px;
                color: #ddd;
                font-size: 14px;
                line-height: 1.6;
            }
        """)
        rv.addWidget(self.ed_detail, 1)

        row = QHBoxLayout()
        self.btn_goto_event = QPushButton("📍 跳转到相关事件")
        self.btn_goto_event.clicked.connect(self._goto_related_event)
        self.btn_goto_event.setEnabled(False)
        self.btn_goto_ending = QPushButton("🎬 跳转到相关结局")
        self.btn_goto_ending.clicked.connect(self._goto_related_ending)
        self.btn_goto_ending.setEnabled(False)
        self.btn_copy_suggestion = QPushButton("📋 复制建议")
        self.btn_copy_suggestion.clicked.connect(self._copy_suggestion)
        self.btn_copy_suggestion.setEnabled(False)
        row.addWidget(self.btn_goto_event)
        row.addWidget(self.btn_goto_ending)
        row.addStretch()
        row.addWidget(self.btn_copy_suggestion)
        rv.addLayout(row)

        body.addWidget(right_frame)
        body.setStretchFactor(0, 1)
        body.setStretchFactor(1, 1)
        ti_layout.addWidget(body)

        self.tabs_view.addTab(tab_issues, "🚩 矛盾列表")

        tab_report = QWidget()
        tr_layout = QVBoxLayout(tab_report)
        tr_layout.setContentsMargins(0, 0, 0, 0)

        report_header = QFrame()
        rh = QHBoxLayout(report_header)
        rh.setContentsMargins(0, 0, 0, 0)
        rh.addWidget(QLabel("📝 复盘看板"))
        rh.addStretch()
        rh.addWidget(QLabel("按维度分组："))
        self.cmb_report_dimension = QComboBox()
        self.cmb_report_dimension.addItems(["🎬 按结局", "📖 按章节", "🔍 按线索", "👥 按角色"])
        self.cmb_report_dimension.currentIndexChanged.connect(self._refresh_report)
        rh.addWidget(self.cmb_report_dimension)
        self.btn_export2 = QPushButton("📤 导出")
        self.btn_export2.clicked.connect(self._export_report)
        self.btn_export2.setEnabled(False)
        rh.addWidget(self.btn_export2)
        tr_layout.addWidget(report_header)

        report_body = QSplitter(Qt.Horizontal)

        report_left = QFrame()
        rlv = QVBoxLayout(report_left)
        rlv.setContentsMargins(0, 0, 0, 0)
        head_ll = QLabel("分组目录（点击查看详情）")
        head_ll.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        head_ll.setStyleSheet("color: #aaa; padding: 4px;")
        rlv.addWidget(head_ll)

        self.tree_report = QTreeWidget()
        self.tree_report.setHeaderLabels(["分组", "问题数", "严重程度"])
        self.tree_report.header().setStretchLastSection(True)
        self.tree_report.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree_report.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree_report.itemSelectionChanged.connect(self._on_report_select)
        self.tree_report.itemDoubleClicked.connect(self._on_report_double_click)
        rlv.addWidget(self.tree_report, 1)
        report_body.addWidget(report_left)

        report_right = QFrame()
        rrv = QVBoxLayout(report_right)
        rrv.setContentsMargins(0, 0, 0, 0)
        head_rr = QLabel("📋 问题详情")
        head_rr.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        head_rr.setStyleSheet("color: #aaa; padding: 4px;")
        rrv.addWidget(head_rr)

        self.report_issue_list = QListWidget()
        self.report_issue_list.itemSelectionChanged.connect(self._on_report_issue_select)
        self.report_issue_list.itemDoubleClicked.connect(self._on_report_issue_double_click)
        rrv.addWidget(self.report_issue_list, 1)

        self.report_detail = QTextEdit()
        self.report_detail.setReadOnly(True)
        self.report_detail.setStyleSheet("""
            QTextEdit {
                background-color: #2a2a35;
                border: 1px solid #44445a;
                border-radius: 4px;
                padding: 10px;
                color: #ddd;
                font-size: 14px;
                line-height: 1.6;
            }
        """)
        rrv.addWidget(self.report_detail, 2)

        btn_row = QHBoxLayout()
        self.btn_report_goto = QPushButton("📍 跳转到修改位置")
        self.btn_report_goto.clicked.connect(self._goto_current_report_issue)
        self.btn_report_goto.setEnabled(False)
        self.btn_report_copy = QPushButton("📋 复制建议")
        self.btn_report_copy.clicked.connect(self._copy_report_suggestion)
        self.btn_report_copy.setEnabled(False)
        btn_row.addWidget(self.btn_report_goto)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_report_copy)
        rrv.addLayout(btn_row)

        report_body.addWidget(report_right)
        report_body.setStretchFactor(0, 1)
        report_body.setStretchFactor(1, 2)
        tr_layout.addWidget(report_body, 1)

        self.tabs_view.addTab(tab_report, "📝 复盘看板")

        root.addWidget(self.tabs_view, 1)

        gb = QGroupBox("📈 全局剧本健康度")
        gv = QVBoxLayout(gb)
        self.lbl_health = QLabel("请点击右上角「全结局一键校验」开始分析...")
        self.lbl_health.setWordWrap(True)
        self.lbl_health.setStyleSheet("font-size: 14px; padding: 6px;")
        gv.addWidget(self.lbl_health)

        self.txt_health_tips = QTextEdit()
        self.txt_health_tips.setReadOnly(True)
        self.txt_health_tips.setFixedHeight(100)
        self.txt_health_tips.setStyleSheet("""
            QTextEdit { background: #2a2a35; border: 1px solid #44445a; border-radius: 4px;
                padding: 6px; color: #ccc; }
        """)
        gv.addWidget(self.txt_health_tips)
        root.addWidget(gb)

        self._current_issue: Optional[Contradiction] = None
        self._current_report_issue: Optional[Contradiction] = None

    def set_data(self, events: List[Event], endings: List[Ending], initial_state: Optional[GameState] = None):
        self._events = events
        self._endings = endings
        if initial_state is not None:
            self._initial_state = initial_state
        self._results_cache.clear()
        self.tree_issues.clear()
        self.tree_report.clear()
        self.report_issue_list.clear()
        self.ed_detail.clear()
        self.report_detail.clear()
        self.lbl_stats.setText("尚未开始校验")
        self.lbl_health.setText("数据已更新，请重新点击「全结局一键校验」。")
        self.txt_health_tips.clear()
        self.btn_export.setEnabled(False)
        self.btn_export2.setEnabled(False)

    def set_cached_result(self, ending: Ending, result: ValidationResult):
        self._results_cache[ending.id] = result
        self._refresh_list()

    def _check_all_endings(self):
        if not self._events or not self._endings:
            QMessageBox.information(self, "提示", "请先添加事件与结局。")
            return
        validator = CausalityValidator(self._events, self._endings, self._initial_state)
        self._results_cache = validator.validate_all_endings(self._initial_state)
        self._refresh_list()
        self._refresh_report()
        self._update_health()
        self.btn_export.setEnabled(True)
        self.btn_export2.setEnabled(True)

    def _collect_all_issues(self) -> List[tuple]:
        raw_issues: List[tuple] = []
        for eid, res in self._results_cache.items():
            ending = next((e for e in self._endings if e.id == eid), None)
            title = ending.title if ending else "(未知结局)"
            for c in res.contradictions:
                if c.severity == "warning" and not self.chk_show_warnings.isChecked():
                    continue
                raw_issues.append((title, c))

        merged_map: Dict[str, Contradiction] = {}
        ending_of_issue: Dict[str, str] = {}
        for title, c in raw_issues:
            key = c.compute_dedup_key()
            if key in merged_map:
                existing = merged_map[key]
                existing.occurrence_count += c.occurrence_count
                for dlg in c.merged_dialogues:
                    if dlg not in existing.merged_dialogues:
                        existing.merged_dialogues.append(dlg)
                if c.dialogue_ref and c.dialogue_ref not in existing.merged_dialogues:
                    existing.merged_dialogues.append(c.dialogue_ref)
            else:
                merged_map[key] = c
                ending_of_issue[key] = title

        result: List[tuple] = []
        for key, c in merged_map.items():
            result.append((ending_of_issue.get(key, "(未知结局)"), c))
        result.sort(key=lambda x: 0 if x[1].severity == "error" else 1)
        return result

    def _refresh_list(self):
        self.tree_issues.clear()
        all_issues = self._collect_all_issues()

        grouped: Dict[str, list] = {}
        for title, c in all_issues:
            key = "🎬 {0}".format(title)
            grouped.setdefault(key, []).append(c)

        for ending_title, issues in grouped.items():
            errors = sum(1 for c in issues if c.severity == "error")
            warns = len(issues) - errors
            top_item = QTreeWidgetItem([
                "错误" if errors else "警告" if warns else "",
                ending_title,
                "{0} 处错误 / {1} 处警告".format(errors, warns),
            ])
            color = COLOR_BROKEN if errors else (COLOR_WARN if warns else COLOR_VALID)
            top_item.setForeground(0, QBrush(color))
            top_item.setForeground(1, QBrush(color))
            top_item.setForeground(2, QBrush(color))
            f = QFont(); f.setBold(True); top_item.setFont(2, f)
            self.tree_issues.addTopLevelItem(top_item)

            for c in issues:
                sev = "❌ 错误" if c.severity == "error" else "⚠ 警告"
                occ_text = " (x{0})".format(c.occurrence_count) if c.occurrence_count > 1 else ""
                sub = QTreeWidgetItem([
                    sev,
                    c.category + occ_text,
                    c.message[:80] + ("..." if len(c.message) > 80 else ""),
                ])
                sub.setData(0, Qt.UserRole, c)
                sc = COLOR_BROKEN if c.severity == "error" else COLOR_WARN
                sub.setForeground(0, QBrush(sc))
                sub.setForeground(1, QBrush(COLOR_INFO))
                sub.setForeground(2, QBrush(QColor(220, 220, 220)))
                top_item.addChild(sub)

        self.tree_issues.expandAll()
        total_err = sum(1 for _, c in all_issues if c.severity == "error")
        total_warn = sum(1 for _, c in all_issues if c.severity == "warning")
        self.lbl_stats.setText(
            "共检测到 {0} 处严重错误，{1} 处警告提示"
            "（涉及 {2} 个结局）".format(total_err, total_warn, len(grouped))
        )

    def _refresh_report(self):
        self.tree_report.clear()
        self.report_issue_list.clear()
        self.report_detail.clear()
        all_issues = self._collect_all_issues()
        if not all_issues:
            return

        dim = self.cmb_report_dimension.currentIndex()

        if dim == 0:
            self._build_report_by_ending(all_issues)
        elif dim == 1:
            self._build_report_by_chapter(all_issues)
        elif dim == 2:
            self._build_report_by_clue(all_issues)
        else:
            self._build_report_by_character(all_issues)

        self.tree_report.expandAll()

    def _build_report_by_ending(self, all_issues: List[tuple]):
        by_ending: Dict[str, List[Contradiction]] = {}
        for ending_title, c in all_issues:
            by_ending.setdefault(ending_title, []).append(c)

        for ending_title in sorted(by_ending.keys()):
            issues = by_ending[ending_title]
            errors = sum(1 for c in issues if c.severity == "error")
            warns = len(issues) - errors
            top = QTreeWidgetItem([
                "🎬 {0}".format(ending_title),
                str(len(issues)),
                "❌{0} ⚠{1}".format(errors, warns) if errors > 0 else "⚠{0}".format(warns),
            ])
            color = COLOR_BROKEN if errors else (COLOR_WARN if warns else COLOR_VALID)
            top.setForeground(0, QBrush(color))
            top.setForeground(2, QBrush(color))
            f = QFont(); f.setBold(True); top.setFont(0, f)
            top.setData(0, Qt.UserRole, ("group", "ending", ending_title, issues))
            self.tree_report.addTopLevelItem(top)

            for c in issues:
                sub = self._make_report_issue_item(c)
                top.addChild(sub)

    def _build_report_by_chapter(self, all_issues: List[tuple]):
        by_chapter: Dict[int, List[tuple]] = {}
        for ending_title, c in all_issues:
            ch = c.related_chapter or 0
            by_chapter.setdefault(ch, []).append((ending_title, c))

        for ch_num in sorted(by_chapter.keys()):
            issues_with_title = by_chapter[ch_num]
            issues = [c for _, c in issues_with_title]
            errors = sum(1 for c in issues if c.severity == "error")
            warns = len(issues) - errors
            label = "第 {0} 章".format(ch_num) if ch_num > 0 else "未指定章节"
            top = QTreeWidgetItem([
                "📖 {0}".format(label),
                str(len(issues)),
                "❌{0} ⚠{1}".format(errors, warns) if errors > 0 else "⚠{0}".format(warns),
            ])
            color = COLOR_BROKEN if errors else (COLOR_WARN if warns else COLOR_VALID)
            top.setForeground(0, QBrush(color))
            top.setForeground(2, QBrush(color))
            f = QFont(); f.setBold(True); top.setFont(0, f)
            top.setData(0, Qt.UserRole, ("group", "chapter", str(ch_num), issues))
            self.tree_report.addTopLevelItem(top)

            for ending_title, c in issues_with_title:
                sub = self._make_report_issue_item(c)
                sub.setText(2, "[{0}] {1}".format(ending_title, sub.text(2)))
                top.addChild(sub)

    def _build_report_by_clue(self, all_issues: List[tuple]):
        by_clue: Dict[str, List[tuple]] = {}
        for ending_title, c in all_issues:
            if c.category in ("台词线索缺失", "结局条件缺失"):
                for ref in self._extract_refs_from_issue(c):
                    if hasattr(ref, 'reference_type') and ref.reference_type == "clue" and ref.reference:
                        by_clue.setdefault(ref.reference, []).append((ending_title, c))

        for clue_name in sorted(by_clue.keys()):
            issues_with_title = by_clue[clue_name]
            issues = [c for _, c in issues_with_title]
            errors = sum(1 for c in issues if c.severity == "error")
            warns = len(issues) - errors
            top = QTreeWidgetItem([
                "🔍 线索「{0}」".format(clue_name),
                str(len(issues)),
                "❌{0} ⚠{1}".format(errors, warns) if errors > 0 else "⚠{0}".format(warns),
            ])
            color = COLOR_BROKEN if errors else (COLOR_WARN if warns else COLOR_VALID)
            top.setForeground(0, QBrush(color))
            top.setForeground(2, QBrush(color))
            f = QFont(); f.setBold(True); top.setFont(0, f)
            top.setData(0, Qt.UserRole, ("group", "clue", clue_name, issues))
            self.tree_report.addTopLevelItem(top)

            for ending_title, c in issues_with_title:
                sub = self._make_report_issue_item(c)
                sub.setText(2, "[{0}] {1}".format(ending_title, sub.text(2)))
                top.addChild(sub)

    def _build_report_by_character(self, all_issues: List[tuple]):
        by_char: Dict[str, List[tuple]] = {}
        for ending_title, c in all_issues:
            if c.category in ("台词角色矛盾", "结局条件缺失"):
                for ref in self._extract_refs_from_issue(c):
                    if hasattr(ref, 'reference_type') and ref.reference_type == "character" and ref.reference:
                        by_char.setdefault(ref.reference, []).append((ending_title, c))

        for char_name in sorted(by_char.keys()):
            issues_with_title = by_char[char_name]
            issues = [c for _, c in issues_with_title]
            errors = sum(1 for c in issues if c.severity == "error")
            warns = len(issues) - errors
            top = QTreeWidgetItem([
                "👥 角色「{0}」".format(char_name),
                str(len(issues)),
                "❌{0} ⚠{1}".format(errors, warns) if errors > 0 else "⚠{0}".format(warns),
            ])
            color = COLOR_BROKEN if errors else (COLOR_WARN if warns else COLOR_VALID)
            top.setForeground(0, QBrush(color))
            top.setForeground(2, QBrush(color))
            f = QFont(); f.setBold(True); top.setFont(0, f)
            top.setData(0, Qt.UserRole, ("group", "character", char_name, issues))
            self.tree_report.addTopLevelItem(top)

            for ending_title, c in issues_with_title:
                sub = self._make_report_issue_item(c)
                sub.setText(2, "[{0}] {1}".format(ending_title, sub.text(2)))
                top.addChild(sub)

    def _make_report_issue_item(self, c: Contradiction) -> QTreeWidgetItem:
        sev = "❌" if c.severity == "error" else "⚠"
        occ_text = " (x{0})".format(c.occurrence_count) if c.occurrence_count > 1 else ""
        item = QTreeWidgetItem([
            sev,
            c.category + occ_text,
            c.message[:60],
        ])
        item.setData(0, Qt.UserRole, ("issue", c))
        sc = COLOR_BROKEN if c.severity == "error" else COLOR_WARN
        item.setForeground(0, QBrush(sc))
        item.setForeground(2, QBrush(QColor(220, 220, 220)))
        return item

    def _extract_refs_from_issue(self, c: Contradiction) -> list:
        if not hasattr(self, "_analyzer"):
            self._analyzer = CausalityValidator(self._events, self._endings, self._initial_state)
        text_parts = [c.message, c.suggestion]
        if c.dialogue_ref:
            text_parts.append(c.dialogue_ref)
        text_parts.extend(c.merged_dialogues)
        text = " ".join(text_parts)
        refs = self._analyzer._dialogue_analyzer.extract_references(text)
        if c.category == "结局条件缺失":
            for cond in self._get_all_conditions():
                if cond.id == c.related_condition_id or cond.human_readable() in c.message:
                    if cond.condition_type.value.startswith("has_clue") or cond.condition_type.value.startswith("no_clue"):
                        refs.append(type("R", (), {
                            "reference_type": "clue",
                            "reference": cond.target or "",
                        })())
                    if cond.condition_type.value.startswith("char_"):
                        refs.append(type("R", (), {
                            "reference_type": "character",
                            "reference": cond.target or "",
                        })())
        return refs

    def _get_all_conditions(self) -> list:
        conds = []
        for e in self._endings:
            conds.extend(e.conditions)
        for ev in self._events:
            conds.extend(ev.conditions)
        return conds

    def _on_select_issue(self):
        items = self.tree_issues.selectedItems()
        if not items:
            return
        issue: Optional[Contradiction] = items[0].data(0, Qt.UserRole)
        self._current_issue = issue
        if issue is None:
            self.ed_detail.clear()
            self.btn_goto_event.setEnabled(False)
            self.btn_goto_ending.setEnabled(False)
            self.btn_copy_suggestion.setEnabled(False)
            return

        self.ed_detail.setHtml(self._render_issue_detail(issue))
        self.btn_goto_event.setEnabled(bool(issue.related_event_id))
        self.btn_goto_ending.setEnabled(bool(issue.related_ending_id))
        self.btn_copy_suggestion.setEnabled(True)

    def _on_double_click_issue(self, item: QTreeWidgetItem, col: int):
        issue: Optional[Contradiction] = item.data(0, Qt.UserRole)
        if issue is None:
            return
        self._navigate_to_issue(issue)

    def _on_report_select(self):
        items = self.tree_report.selectedItems()
        self.report_issue_list.clear()
        if not items:
            return
        data = items[0].data(0, Qt.UserRole)
        if data and isinstance(data, tuple) and len(data) >= 4:
            issues = data[3]
            for c in issues:
                sev = "❌" if c.severity == "error" else "⚠"
                occ_text = " (x{0})".format(c.occurrence_count) if c.occurrence_count > 1 else ""
                item = QListWidgetItem("{0} {1}{2}：{3}".format(
                    sev, c.category, occ_text, c.message[:60]
                ))
                item.setData(Qt.UserRole, c)
                if c.severity == "error":
                    item.setForeground(QBrush(COLOR_BROKEN))
                else:
                    item.setForeground(QBrush(COLOR_WARN))
                self.report_issue_list.addItem(item)

    def _on_report_issue_select(self):
        items = self.report_issue_list.selectedItems()
        if not items:
            self._current_report_issue = None
            self.report_detail.clear()
            self.btn_report_goto.setEnabled(False)
            self.btn_report_copy.setEnabled(False)
            return
        issue = items[0].data(Qt.UserRole)
        self._current_report_issue = issue
        self.report_detail.setHtml(self._render_issue_detail(issue))
        self.btn_report_goto.setEnabled(True)
        self.btn_report_copy.setEnabled(True)

    def _on_report_double_click(self, item: QTreeWidgetItem, col: int):
        data = item.data(0, Qt.UserRole)
        if data and isinstance(data, tuple) and len(data) >= 2:
            if data[0] == "issue":
                self._navigate_to_issue(data[1])

    def _on_report_issue_double_click(self, item: QListWidgetItem):
        issue = item.data(Qt.UserRole)
        if issue:
            self._navigate_to_issue(issue)

    def _goto_current_report_issue(self):
        if self._current_report_issue:
            self._navigate_to_issue(self._current_report_issue)

    def _copy_report_suggestion(self):
        if self._current_report_issue:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(self._current_report_issue.suggestion)
            self.btn_report_copy.setText("✅ 已复制！")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(1500, lambda: self.btn_report_copy.setText("📋 复制建议"))

    def _navigate_to_issue(self, issue: Contradiction):
        nav_type = issue.nav_target_type
        nav_id = issue.nav_target_id
        if nav_type == "event" and nav_id:
            self.navigate_event_requested.emit(nav_id)
        elif nav_type == "ending" and nav_id:
            self.navigate_ending_requested.emit(nav_id)
        elif issue.related_event_id:
            self.navigate_event_requested.emit(issue.related_event_id)
        elif issue.related_ending_id:
            self.navigate_ending_requested.emit(issue.related_ending_id)

    def _goto_related_event(self):
        if self._current_issue:
            target = self._current_issue.nav_target_id or self._current_issue.related_event_id
            target_type = self._current_issue.nav_target_type
            if target_type == "ending" and self._current_issue.related_ending_id:
                self.navigate_ending_requested.emit(self._current_issue.related_ending_id)
            elif target:
                self.navigate_event_requested.emit(target)

    def _goto_related_ending(self):
        if self._current_issue and self._current_issue.related_ending_id:
            self.navigate_ending_requested.emit(self._current_issue.related_ending_id)

    def _copy_suggestion(self):
        if self._current_issue:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(self._current_issue.suggestion)
            self.btn_copy_suggestion.setText("✅ 已复制！")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(1500, lambda: self.btn_copy_suggestion.setText("📋 复制建议"))

    def _export_report(self):
        if not self._results_cache:
            QMessageBox.information(self, "提示", "请先运行校验。")
            return

        options = QFileDialog.Options()
        file_name, filter_used = QFileDialog.getSaveFileName(
            self, "导出审稿报告", "剧本审稿报告.md",
            "Markdown 文件 (*.md);;纯文本文件 (*.txt);;所有文件 (*.*)",
            options=options,
        )
        if not file_name:
            return

        is_md = filter_used.startswith("Markdown") or file_name.lower().endswith(".md")
        report = self._generate_export_report(is_md)

        try:
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(report)
            QMessageBox.information(self, "成功", "审稿报告已导出到：\n{0}".format(file_name))
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def _generate_export_report(self, markdown: bool = True) -> str:
        validator = CausalityValidator(self._events, self._endings, self._initial_state)
        entities = validator.get_known_entities()

        lines = []
        if markdown:
            lines.append("# 剧本因果链审稿报告")
            lines.append("")
            lines.append("*生成日期：{0}*".format("2026-06-19"))
            lines.append("")
            lines.append("## 剧本概况")
            lines.append("")
            lines.append("- **事件总数**：{0}".format(len(self._events)))
            lines.append("- **结局总数**：{0}".format(len(self._endings)))
            lines.append("- **涉及线索**：{0} 条".format(len(entities.get("clues", []))))
            lines.append("- **涉及角色**：{0} 名".format(len(entities.get("characters", []))))
            lines.append("- **涉及地点**：{0} 处".format(len(entities.get("locations", []))))
            lines.append("")
        else:
            lines.append("=" * 60)
            lines.append("剧本因果链审稿报告")
            lines.append("生成日期：2026-06-19")
            lines.append("=" * 60)
            lines.append("")
            lines.append("【剧本概况】")
            lines.append("  事件总数：{0}".format(len(self._events)))
            lines.append("  结局总数：{0}".format(len(self._endings)))
            lines.append("  涉及线索：{0} 条".format(len(entities.get("clues", []))))
            lines.append("  涉及角色：{0} 名".format(len(entities.get("characters", []))))
            lines.append("  涉及地点：{0} 处".format(len(entities.get("locations", []))))
            lines.append("")

        total_errors = 0
        total_warnings = 0
        for res in self._results_cache.values():
            total_errors += sum(1 for c in res.contradictions if c.severity == "error")
            total_warnings += sum(1 for c in res.contradictions if c.severity == "warning")

        if markdown:
            lines.append("## 健康度评估")
            lines.append("")
            lines.append("- **严重错误**：{0} 处".format(total_errors))
            lines.append("- **警告提示**：{0} 处".format(total_warnings))
            health_pct = max(0, 100 - total_errors * 10 - total_warnings * 3)
            health_level = "优秀" if health_pct >= 80 else ("良好" if health_pct >= 60 else ("待改进" if health_pct >= 40 else "需修复"))
            lines.append("- **健康评分**：{0}/100（{1}）".format(health_pct, health_level))
            lines.append("")
        else:
            lines.append("【健康度评估】")
            lines.append("  严重错误：{0} 处".format(total_errors))
            lines.append("  警告提示：{0} 处".format(total_warnings))
            health_pct = max(0, 100 - total_errors * 10 - total_warnings * 3)
            health_level = "优秀" if health_pct >= 80 else ("良好" if health_pct >= 60 else ("待改进" if health_pct >= 40 else "需修复"))
            lines.append("  健康评分：{0}/100（{1}）".format(health_pct, health_level))
            lines.append("")

        all_issues = self._collect_all_issues()

        if markdown:
            lines.append("## 按结局分类问题")
            lines.append("")
            by_ending: Dict[str, List[tuple]] = {}
            for title, c in all_issues:
                by_ending.setdefault(title, []).append((title, c))
            for ending_title in sorted(by_ending.keys()):
                lines.append("### {0}".format(ending_title))
                lines.append("")
                issues = by_ending[ending_title]
                for _, c in issues:
                    lines.append(self._format_issue(c, markdown))
                lines.append("")
        else:
            lines.append("=" * 60)
            lines.append("【按结局分类问题】")
            lines.append("=" * 60)
            by_ending: Dict[str, List[tuple]] = {}
            for title, c in all_issues:
                by_ending.setdefault(title, []).append((title, c))
            for ending_title in sorted(by_ending.keys()):
                lines.append("")
                lines.append("【{0}】".format(ending_title))
                issues = by_ending[ending_title]
                for _, c in issues:
                    lines.append(self._format_issue(c, markdown))
                lines.append("")

        if markdown:
            lines.append("## 按章节分类问题")
            lines.append("")
            by_chapter: Dict[int, List[tuple]] = {}
            for title, c in all_issues:
                ch = c.related_chapter or 0
                by_chapter.setdefault(ch, []).append((title, c))
            for ch_num in sorted(by_chapter.keys()):
                label = "第 {0} 章".format(ch_num) if ch_num > 0 else "未指定章节"
                lines.append("### {0}".format(label))
                lines.append("")
                for title, c in by_chapter[ch_num]:
                    lines.append(self._format_issue(c, markdown, title))
                lines.append("")
        else:
            lines.append("=" * 60)
            lines.append("【按章节分类问题】")
            lines.append("=" * 60)
            by_chapter: Dict[int, List[tuple]] = {}
            for title, c in all_issues:
                ch = c.related_chapter or 0
                by_chapter.setdefault(ch, []).append((title, c))
            for ch_num in sorted(by_chapter.keys()):
                label = "第 {0} 章".format(ch_num) if ch_num > 0 else "未指定章节"
                lines.append("")
                lines.append("【{0}】".format(label))
                for title, c in by_chapter[ch_num]:
                    lines.append(self._format_issue(c, markdown, title))
                lines.append("")

        if markdown:
            lines.append("## 按线索分类问题")
            lines.append("")
            by_clue: Dict[str, List[tuple]] = {}
            for title, c in all_issues:
                if c.category in ("台词线索缺失", "结局条件缺失"):
                    for ref in self._extract_refs_from_issue(c):
                        if hasattr(ref, 'reference_type') and ref.reference_type == "clue" and ref.reference:
                            by_clue.setdefault(ref.reference, []).append((title, c))
            for clue_name in sorted(by_clue.keys()):
                lines.append("### 线索「{0}」".format(clue_name))
                lines.append("")
                for title, c in by_clue[clue_name]:
                    lines.append(self._format_issue(c, markdown, title))
                lines.append("")

            lines.append("## 按角色分类问题")
            lines.append("")
            by_char: Dict[str, List[tuple]] = {}
            for title, c in all_issues:
                if c.category in ("台词角色矛盾", "结局条件缺失"):
                    for ref in self._extract_refs_from_issue(c):
                        if hasattr(ref, 'reference_type') and ref.reference_type == "character" and ref.reference:
                            by_char.setdefault(ref.reference, []).append((title, c))
            for char_name in sorted(by_char.keys()):
                lines.append("### 角色「{0}」".format(char_name))
                lines.append("")
                for title, c in by_char[char_name]:
                    lines.append(self._format_issue(c, markdown, title))
                lines.append("")
        else:
            lines.append("=" * 60)
            lines.append("【按线索分类问题】")
            lines.append("=" * 60)
            by_clue: Dict[str, List[tuple]] = {}
            for title, c in all_issues:
                if c.category in ("台词线索缺失", "结局条件缺失"):
                    for ref in self._extract_refs_from_issue(c):
                        if hasattr(ref, 'reference_type') and ref.reference_type == "clue" and ref.reference:
                            by_clue.setdefault(ref.reference, []).append((title, c))
            for clue_name in sorted(by_clue.keys()):
                lines.append("")
                lines.append("【线索「{0}」】".format(clue_name))
                for title, c in by_clue[clue_name]:
                    lines.append(self._format_issue(c, markdown, title))
                lines.append("")

            lines.append("=" * 60)
            lines.append("【按角色分类问题】")
            lines.append("=" * 60)
            by_char: Dict[str, List[tuple]] = {}
            for title, c in all_issues:
                if c.category in ("台词角色矛盾", "结局条件缺失"):
                    for ref in self._extract_refs_from_issue(c):
                        if hasattr(ref, 'reference_type') and ref.reference_type == "character" and ref.reference:
                            by_char.setdefault(ref.reference, []).append((title, c))
            for char_name in sorted(by_char.keys()):
                lines.append("")
                lines.append("【角色「{0}」】".format(char_name))
                for title, c in by_char[char_name]:
                    lines.append(self._format_issue(c, markdown, title))
                lines.append("")

        if markdown:
            lines.append("---")
            lines.append("*本报告由因果链校验器自动生成*")
        else:
            lines.append("=" * 60)
            lines.append("本报告由因果链校验器自动生成")
            lines.append("=" * 60)

        return "\n".join(lines)

    def _format_issue(self, c: Contradiction, markdown: bool, ending_title: Optional[str] = None) -> str:
        sev_icon = "❌" if c.severity == "error" else "⚠"
        occ_text = " (出现{0}次)".format(c.occurrence_count) if c.occurrence_count > 1 else ""

        if markdown:
            parts = []
            parts.append("- {0} **{1}**{2}".format(sev_icon, c.category, occ_text))
            parts.append("  - 问题：{0}".format(c.message))
            if ending_title:
                parts.append("  - 相关结局：{0}".format(ending_title))
            if c.related_chapter:
                parts.append("  - 建议章节：第 {0} 章".format(c.related_chapter))
            if c.merged_dialogues and len(c.merged_dialogues) > 1:
                for i, dlg in enumerate(c.merged_dialogues):
                    parts.append("  - 相关台词{0}：「{1}」".format(i + 1, dlg))
            elif c.dialogue_ref:
                parts.append("  - 相关台词：「{0}」".format(c.dialogue_ref))
            parts.append("  - 修改建议：{0}".format(c.suggestion))
            return "\n".join(parts)
        else:
            parts = []
            parts.append("  {0} {1}{2}".format(sev_icon, c.category, occ_text))
            parts.append("     问题：{0}".format(c.message))
            if ending_title:
                parts.append("     相关结局：{0}".format(ending_title))
            if c.related_chapter:
                parts.append("     建议章节：第 {0} 章".format(c.related_chapter))
            if c.merged_dialogues and len(c.merged_dialogues) > 1:
                for i, dlg in enumerate(c.merged_dialogues):
                    parts.append("     相关台词{0}：「{1}」".format(i + 1, dlg))
            elif c.dialogue_ref:
                parts.append("     相关台词：「{0}」".format(c.dialogue_ref))
            parts.append("     修改建议：{0}".format(c.suggestion))
            return "\n".join(parts)

    def _update_health(self):
        if not self._results_cache:
            return
        total = len(self._results_cache)
        valid = 0
        warn = 0
        broken = 0
        for res in self._results_cache.values():
            if res.overall_status == LinkStatus.VALID:
                valid += 1
            elif res.overall_status == LinkStatus.WARN:
                warn += 1
            else:
                broken += 1
        pct = (valid + warn * 0.5) / max(total, 1) * 100
        if pct >= 80:
            color = COLOR_VALID.name()
            verdict = "整体良好"
        elif pct >= 50:
            color = COLOR_WARN.name()
            verdict = "有待完善"
        else:
            color = COLOR_BROKEN.name()
            verdict = "需要修复"
        self.lbl_health.setText(
            "<b>剧本健康度：<span style='color: {0}; font-size: 18px;'>{1:.0f}%</span> — {2}</b><br>"
            "共 {3} 个结局：✅ 完整 {4} 个 · ⚠ 有警告 {5} 个 · ❌ 断裂 {6} 个".format(
                color, pct, verdict, total, valid, warn, broken
            )
        )

        tips = []
        if broken:
            tips.append("🔧 建议优先修复 ❌ 断裂结局的条件缺失问题。")
        if warn:
            tips.append("⚠ 有警告的结局虽然可达成，但部分路径并非最优，建议检查是否符合设计意图。")
        clues_used = set()
        for res in self._results_cache.values():
            for c in res.ending_met_conditions + res.ending_missing_conditions:
                if c.condition_type.value.startswith("has_clue") or c.condition_type.value.startswith("no_clue"):
                    clues_used.add(c.target)
        if clues_used:
            tips.append("💡 当前剧本涉及线索 {0} 条：{1}".format(len(clues_used), ", ".join(sorted(clues_used)[:8])))
        chars = set()
        for res in self._results_cache.values():
            if res.final_state:
                chars.update(res.final_state.characters.keys())
        if chars:
            tips.append("👥 涉及角色 {0} 名：{1}".format(len(chars), ", ".join(sorted(chars))))
        if not tips:
            tips.append("开始写作吧！先构思事件，再为每个结局定义必要条件。")
        self.txt_health_tips.setPlainText("\n".join("• {0}".format(t) for t in tips))

    def _render_issue_detail(self, issue: Contradiction) -> str:
        sev_label = "严重错误" if issue.severity == "error" else "建议改进"
        sev_color = COLOR_BROKEN if issue.severity == "error" else COLOR_WARN

        related_parts = []
        if issue.related_event_id:
            ev = next((e for e in self._events if e.id == issue.related_event_id), None)
            if ev:
                related_parts.append("相关事件：第{0}章「{1}」".format(ev.chapter, ev.title))
        if issue.related_ending_id:
            end = next((e for e in self._endings if e.id == issue.related_ending_id), None)
            if end:
                related_parts.append("相关结局：「{0}」".format(end.title))
        if issue.related_chapter:
            related_parts.append("建议回第 {0} 章检查".format(issue.related_chapter))

        nav_hint = ""
        if issue.nav_target_type == "event":
            nav_hint = "📍 双击可跳转到事件录入修改"
        elif issue.nav_target_type == "ending":
            nav_hint = "📍 双击可跳转到结局编辑修改"
        if nav_hint:
            related_parts.append(nav_hint)

        related_text = "；".join(related_parts) if related_parts else "（无关联对象）"

        path_state_block = ""
        if issue.related_ending_id and issue.related_ending_id in self._results_cache:
            result = self._results_cache[issue.related_ending_id]
            if result.final_state:
                fs = result.final_state
                state_parts = ["恐惧值: {0}".format(fs.fear_level)]
                clues_on = [k for k, v in fs.clues.items() if v]
                if clues_on:
                    state_parts.append("线索({0}): {1}".format(len(clues_on), ", ".join(clues_on[:5])))
                dead_chars = [k for k, v in fs.characters.items() if v.value != "alive"]
                if dead_chars:
                    state_parts.append("非存活角色: {0}".format(", ".join(dead_chars)))
                path_state_block = """
                <div style="background: #2e2e3e; padding: 10px; border-radius: 6px; margin-bottom: 12px; border: 1px solid #444;">
                    <b style="color: #aaccff;">📊 当前路径状态：</b><br>
                    <span style="color: #ccc;">{0}</span>
                </div>
                """.format(" ｜ ".join(state_parts))

        dialogue_block = ""
        if issue.merged_dialogues and len(issue.merged_dialogues) > 1:
            dialogue_html = "<br>".join(
                "「{0}」".format(d) for d in issue.merged_dialogues
            )
            dialogue_block = """
            <div style="background: #3a2e2e; padding: 10px; border-radius: 6px; margin-bottom: 12px; border-left: 4px solid #ff9999;">
                <b style="color: #ffcc99;">🎬 相关台词（共 {0} 处引用）：</b><br>
                <span style="color: #fff; font-style: italic;">{1}</span>
            </div>
            """.format(len(issue.merged_dialogues), dialogue_html)
        elif issue.dialogue_ref:
            dialogue_block = """
            <div style="background: #3a2e2e; padding: 10px; border-radius: 6px; margin-bottom: 12px; border-left: 4px solid #ff9999;">
                <b style="color: #ffcc99;">🎬 相关台词：</b><br>
                <span style="color: #fff; font-style: italic;">「{0}」</span>
            </div>
            """.format(issue.dialogue_ref)

        occ_block = ""
        if issue.occurrence_count > 1:
            occ_block = """
            <div style="background: #3e3e2e; padding: 8px; border-radius: 6px; margin-bottom: 12px;">
                <b style="color: #ffcc66;">📌 该问题在多条台词中重复出现，共 {0} 次</b>
            </div>
            """.format(issue.occurrence_count)

        html = """
        <div style="padding: 4px;">
            <h3 style="color: {0}; margin: 0 0 10px 0;">【{1}】{2}</h3>
            {3}
            {4}
            {5}
            <div style="background: #333340; padding: 10px; border-radius: 6px; margin-bottom: 12px;">
                <b style="color: #ffcc99;">💬 具体问题：</b><br>
                <span style="color: #fff;">{6}</span>
            </div>
            <div style="background: #2e3b2e; padding: 10px; border-radius: 6px; margin-bottom: 12px; border: 1px solid #3e5b3e;">
                <b style="color: #9fe59f;">💡 修改建议：</b><br>
                <span style="color: #e6ffe6;">{7}</span>
            </div>
            <div style="color: #888; font-size: 12px;">
                📍 关联信息：{8}
            </div>
        </div>
        """.format(
            sev_color.name(), sev_label, issue.category,
            occ_block, dialogue_block, path_state_block,
            issue.message, issue.suggestion, related_text
        )
        return html
