import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import List, Optional, Dict, Set
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTreeWidget,
    QTreeWidgetItem, QComboBox, QLineEdit, QTextEdit,
    QListWidget, QListWidgetItem, QMessageBox,
    QGroupBox, QScrollArea, QSplitter, QFrame, QTabWidget,
    QSizePolicy, QCheckBox, QHeaderView, QTableWidget, QTableWidgetItem,
    QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor, QBrush

from models import Event, Ending, Condition, GameState
from services.validator import (
    CausalityValidator, ValidationResult, LinkStatus, Contradiction,
    BranchPreview,
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

        report_header = QLabel("📝 审稿报告（按类别归档，双击跳转定位）")
        report_header.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        report_header.setStyleSheet("color: #aaa; padding: 4px;")
        tr_layout.addWidget(report_header)

        self.tree_report = QTreeWidget()
        self.tree_report.setHeaderLabels(["分类维度", "问题摘要", "关联台词/补写位置"])
        self.tree_report.header().setStretchLastSection(True)
        self.tree_report.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree_report.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tree_report.itemDoubleClicked.connect(self._on_report_double_click)
        tr_layout.addWidget(self.tree_report, 1)

        self.tabs_view.addTab(tab_report, "📝 审稿报告")

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

    def set_data(self, events: List[Event], endings: List[Ending], initial_state: Optional[GameState] = None):
        self._events = events
        self._endings = endings
        if initial_state is not None:
            self._initial_state = initial_state
        self._results_cache.clear()
        self.tree_issues.clear()
        self.tree_report.clear()
        self.ed_detail.clear()
        self.lbl_stats.setText("尚未开始校验")
        self.lbl_health.setText("数据已更新，请重新点击「全结局一键校验」。")
        self.txt_health_tips.clear()

    def set_cached_result(self, ending: Ending, result: ValidationResult):
        self._results_cache[ending.id] = result
        self._refresh_list()

    def _check_all_endings(self):
        if not self._events or not self._endings:
            QMessageBox.information(self, "提示", "请先添加事件与结局。")
            return
        validator = CausalityValidator(self._events, self._endings, self._initial_state)
        self._results_cache = validator.validate_all_endings(self._initial_state)
        for eid, res in self._results_cache.items():
            ending = next((e for e in self._endings if e.id == eid), None)
            if ending:
                extra = validator.find_dialogue_contradictions(res, ending)
                res.contradictions.extend(extra)
        self._refresh_list()
        self._refresh_report()
        self._update_health()

    def _collect_all_issues(self) -> List[tuple]:
        all_issues: List[tuple] = []
        for eid, res in self._results_cache.items():
            ending = next((e for e in self._endings if e.id == eid), None)
            title = ending.title if ending else "(未知结局)"
            for c in res.contradictions:
                if c.severity == "warning" and not self.chk_show_warnings.isChecked():
                    continue
                all_issues.append((title, c))
        all_issues.sort(key=lambda x: 0 if x[1].severity == "error" else 1)
        return all_issues

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
                sub = QTreeWidgetItem([sev, c.category, c.message[:80] + ("..." if len(c.message) > 80 else "")])
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
        all_issues = self._collect_all_issues()

        by_category: Dict[str, List[tuple]] = {}
        for ending_title, c in all_issues:
            by_category.setdefault(c.category, []).append((ending_title, c))

        cat_order = ["事件条件冲突", "结局条件缺失", "台词线索缺失", "台词角色矛盾", "台词地点缺失"]
        for cat in cat_order:
            if cat not in by_category:
                continue
            issues = by_category[cat]
            errors = sum(1 for _, c in issues if c.severity == "error")
            warns = len(issues) - errors
            cat_item = QTreeWidgetItem([
                "{0} ({1})".format(cat, len(issues)),
                "{0} 严重 / {1} 警告".format(errors, warns),
                "",
            ])
            cat_color = COLOR_BROKEN if errors else COLOR_WARN
            cat_item.setForeground(0, QBrush(cat_color))
            f = QFont(); f.setBold(True); cat_item.setFont(0, f)
            self.tree_report.addTopLevelItem(cat_item)

            by_ending: Dict[str, List[tuple]] = {}
            for ending_title, c in issues:
                by_ending.setdefault(ending_title, []).append(c)

            for ending_title, ending_issues in by_ending.items():
                end_item = QTreeWidgetItem([
                    "🎬 " + ending_title,
                    "{0} 个问题".format(len(ending_issues)),
                    "",
                ])
                end_item.setForeground(0, QBrush(COLOR_INFO))
                cat_item.addChild(end_item)

                for c in ending_issues:
                    dialogue_hint = ""
                    if c.dialogue_ref:
                        dialogue_hint = "台词: {0}".format(c.dialogue_ref[:50])
                    chapter_hint = ""
                    if c.related_chapter:
                        chapter_hint = "→ 第{0}章补写".format(c.related_chapter)

                    sub = QTreeWidgetItem([
                        "❌" if c.severity == "error" else "⚠",
                        c.message[:80],
                        "{0} {1}".format(dialogue_hint, chapter_hint).strip(),
                    ])
                    sub.setData(0, Qt.UserRole, c)
                    sc = COLOR_BROKEN if c.severity == "error" else COLOR_WARN
                    sub.setForeground(0, QBrush(sc))
                    sub.setForeground(1, QBrush(QColor(220, 220, 220)))
                    if c.dialogue_ref:
                        sub.setForeground(2, QBrush(QColor(255, 200, 150)))
                    else:
                        sub.setForeground(2, QBrush(COLOR_VALID))
                    end_item.addChild(sub)

        by_chapter: Dict[int, List[tuple]] = {}
        for ending_title, c in all_issues:
            ch = c.related_chapter or 0
            by_chapter.setdefault(ch, []).append((ending_title, c))

        if by_chapter:
            chap_root = QTreeWidgetItem([
                "📖 按章节归档 ({0} 章)".format(len(by_chapter)),
                "",
                "",
            ])
            chap_root.setForeground(0, QBrush(COLOR_INFO))
            f2 = QFont(); f2.setBold(True); chap_root.setFont(0, f2)
            self.tree_report.addTopLevelItem(chap_root)

            for ch_num in sorted(by_chapter.keys()):
                ch_issues = by_chapter[ch_num]
                ch_label = "第 {0} 章".format(ch_num) if ch_num > 0 else "未指定章节"
                ch_item = QTreeWidgetItem([
                    ch_label,
                    "{0} 个问题".format(len(ch_issues)),
                    "",
                ])
                chap_root.addChild(ch_item)
                for ending_title, c in ch_issues:
                    sub = QTreeWidgetItem([
                        "❌" if c.severity == "error" else "⚠",
                        "[{0}] {1}".format(ending_title, c.message[:60]),
                        c.category,
                    ])
                    sub.setData(0, Qt.UserRole, c)
                    sc = COLOR_BROKEN if c.severity == "error" else COLOR_WARN
                    sub.setForeground(0, QBrush(sc))
                    ch_item.addChild(sub)

        self.tree_report.expandAll()
        for i in range(3):
            self.tree_report.resizeColumnToContents(i)

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

    def _on_report_double_click(self, item: QTreeWidgetItem, col: int):
        issue: Optional[Contradiction] = item.data(0, Qt.UserRole)
        if issue is None:
            return
        self._navigate_to_issue(issue)

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
        if issue.dialogue_ref:
            dialogue_block = """
            <div style="background: #3a2e2e; padding: 10px; border-radius: 6px; margin-bottom: 12px; border-left: 4px solid #ff9999;">
                <b style="color: #ffcc99;">🎬 相关台词：</b><br>
                <span style="color: #fff; font-style: italic;">「{0}」</span>
            </div>
            """.format(issue.dialogue_ref)

        html = """
        <div style="padding: 4px;">
            <h3 style="color: {0}; margin: 0 0 10px 0;">【{1}】{2}</h3>
            {3}
            {4}
            <div style="background: #333340; padding: 10px; border-radius: 6px; margin-bottom: 12px;">
                <b style="color: #ffcc99;">💬 具体问题：</b><br>
                <span style="color: #fff;">{5}</span>
            </div>
            <div style="background: #2e3b2e; padding: 10px; border-radius: 6px; margin-bottom: 12px; border: 1px solid #3e5b3e;">
                <b style="color: #9fe59f;">💡 修改建议：</b><br>
                <span style="color: #e6ffe6;">{6}</span>
            </div>
            <div style="color: #888; font-size: 12px;">
                📍 关联信息：{7}
            </div>
        </div>
        """.format(
            sev_color.name(), sev_label, issue.category,
            dialogue_block, path_state_block,
            issue.message, issue.suggestion, related_text
        )
        return html
