import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import List, Optional, Callable
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTreeWidget,
    QTreeWidgetItem, QComboBox, QSpinBox, QLineEdit, QTextEdit,
    QFormLayout, QListWidget, QListWidgetItem, QMessageBox,
    QGroupBox, QScrollArea, QSplitter, QFrame, QInputDialog, QAbstractItemView,
    QHeaderView,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor, QBrush, QIcon

from models import (
    Event, Ending, Condition, ConditionType, Choice, ChoiceEffect,
    ChoiceEffectType, GameState,
)
from .common import (
    apply_dark_style, ConditionEditDialog, EffectEditDialog,
    COLOR_BROKEN, COLOR_VALID, COLOR_WARN, COLOR_INFO,
)


class EventInputPanel(QWidget):
    data_changed = Signal()

    def __init__(self, events: List[Event], endings: List[Ending], initial_state: Optional[GameState] = None, parent=None):
        super().__init__(parent)
        self._events = events
        self._endings = endings
        self._initial_state = initial_state or GameState()
        self._current_event: Optional[Event] = None
        self._build_ui()
        self._refresh_event_tree()

    def _build_ui(self):
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(8)

        left_panel = QFrame()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_panel.setFixedWidth(320)

        header = QLabel("📖 章节与事件")
        header.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        header.setStyleSheet(f"color: #9ecbff; padding: 4px;")
        left_layout.addWidget(header)

        self.tree_events = QTreeWidget()
        self.tree_events.setHeaderLabels(["名称", "章节"])
        self.tree_events.header().setStretchLastSection(False)
        self.tree_events.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree_events.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree_events.itemSelectionChanged.connect(self._on_select_event)
        left_layout.addWidget(self.tree_events, 1)

        btns = QHBoxLayout()
        btn_add_ch = QPushButton("+ 新增章节")
        btn_add_ch.clicked.connect(self._add_chapter_dialog)
        btn_add_ev = QPushButton("+ 新增事件")
        btn_add_ev.clicked.connect(self._add_event)
        btn_del = QPushButton("删除")
        btn_del.setProperty("danger", True)
        btn_del.clicked.connect(self._delete_selected)
        btns.addWidget(btn_add_ch)
        btns.addWidget(btn_add_ev)
        btns.addWidget(btn_del)
        left_layout.addLayout(btns)

        self.lbl_count = QLabel()
        self.lbl_count.setStyleSheet("color: #999; padding: 2px;")
        left_layout.addWidget(self.lbl_count)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        right_panel = QFrame()
        self.right_layout = QVBoxLayout(right_panel)
        self.right_layout.setContentsMargins(4, 4, 4, 4)
        self.right_layout.setSpacing(8)

        self._build_initial_state_editor()
        self._build_event_editor()

        scroll.setWidget(right_panel)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root_layout.addWidget(splitter)

    def _build_initial_state_editor(self):
        gb = QGroupBox("🎬 剧本开局初始状态")
        v = QVBoxLayout(gb)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("开局恐惧值："))
        self.sp_initial_fear = QSpinBox()
        self.sp_initial_fear.setRange(0, 100)
        self.sp_initial_fear.setToolTip("游戏开始时玩家的恐惧值")
        self.sp_initial_fear.valueChanged.connect(self._on_initial_fear_change)
        row1.addWidget(self.sp_initial_fear)
        row1.addStretch()

        btn_add_flag = QPushButton("+ 添加开局标记")
        btn_add_flag.clicked.connect(self._add_initial_flag)
        btn_add_clue = QPushButton("+ 添加初始线索")
        btn_add_clue.clicked.connect(self._add_initial_clue)
        btn_add_char = QPushButton("+ 添加初始角色")
        btn_add_char.clicked.connect(self._add_initial_character)
        row1.addWidget(btn_add_flag)
        row1.addWidget(btn_add_clue)
        row1.addWidget(btn_add_char)
        v.addLayout(row1)

        row2 = QHBoxLayout()
        col_flags = QVBoxLayout()
        col_flags.addWidget(QLabel("🏷 开局标记："))
        self.lst_initial_flags = QListWidget()
        self.lst_initial_flags.setFixedHeight(80)
        self.lst_initial_flags.itemDoubleClicked.connect(self._edit_initial_flag)
        col_flags.addWidget(self.lst_initial_flags)
        row_flag_btns = QHBoxLayout()
        btn_flag_del = QPushButton("删除")
        btn_flag_del.setProperty("danger", True)
        btn_flag_del.clicked.connect(self._del_initial_flag)
        row_flag_btns.addWidget(btn_flag_del)
        row_flag_btns.addStretch()
        col_flags.addLayout(row_flag_btns)
        row2.addLayout(col_flags, 1)

        col_clues = QVBoxLayout()
        col_clues.addWidget(QLabel("💡 初始线索："))
        self.lst_initial_clues = QListWidget()
        self.lst_initial_clues.setFixedHeight(80)
        self.lst_initial_clues.itemDoubleClicked.connect(self._edit_initial_clue)
        col_clues.addWidget(self.lst_initial_clues)
        row_clue_btns = QHBoxLayout()
        btn_clue_del = QPushButton("删除")
        btn_clue_del.setProperty("danger", True)
        btn_clue_del.clicked.connect(self._del_initial_clue)
        row_clue_btns.addWidget(btn_clue_del)
        row_clue_btns.addStretch()
        col_clues.addLayout(row_clue_btns)
        row2.addLayout(col_clues, 1)

        col_chars = QVBoxLayout()
        col_chars.addWidget(QLabel("👥 初始角色状态："))
        self.lst_initial_chars = QListWidget()
        self.lst_initial_chars.setFixedHeight(80)
        self.lst_initial_chars.itemDoubleClicked.connect(self._edit_initial_char)
        col_chars.addWidget(self.lst_initial_chars)
        row_char_btns = QHBoxLayout()
        btn_char_del = QPushButton("删除")
        btn_char_del.setProperty("danger", True)
        btn_char_del.clicked.connect(self._del_initial_char)
        row_char_btns.addWidget(btn_char_del)
        row_char_btns.addStretch()
        col_chars.addLayout(row_char_btns)
        row2.addLayout(col_chars, 1)

        v.addLayout(row2)
        self.right_layout.addWidget(gb)

    def _refresh_initial_state_editor(self):
        self.sp_initial_fear.blockSignals(True)
        self.sp_initial_fear.setValue(self._initial_state.fear_level)
        self.sp_initial_fear.blockSignals(False)

        self.lst_initial_flags.clear()
        for k, v in self._initial_state.flags.items():
            item = QListWidgetItem(f"{'✓' if v else '✗'} {k}")
            item.setData(Qt.UserRole, k)
            item.setForeground(QBrush(COLOR_VALID if v else COLOR_BROKEN))
            self.lst_initial_flags.addItem(item)

        self.lst_initial_clues.clear()
        for k, v in self._initial_state.clues.items():
            item = QListWidgetItem(f"{'✓' if v else '✗'} {k}")
            item.setData(Qt.UserRole, k)
            item.setForeground(QBrush(COLOR_VALID if v else COLOR_BROKEN))
            self.lst_initial_clues.addItem(item)

        self.lst_initial_chars.clear()
        for k, v in self._initial_state.characters.items():
            label = {
                "alive": "存活", "dead": "死亡", "missing": "失踪", "insane": "发疯"
            }.get(v.value, v.value)
            color = COLOR_VALID if v.value == "alive" else COLOR_BROKEN
            item = QListWidgetItem(f"{k} → {label}")
            item.setData(Qt.UserRole, k)
            item.setForeground(QBrush(color))
            self.lst_initial_chars.addItem(item)

    def _on_initial_fear_change(self, val: int):
        self._initial_state.fear_level = val
        self.data_changed.emit()

    def _add_initial_flag(self):
        name, ok = QInputDialog.getText(self, "添加开局标记", "标记ID（英文/拼音，如 已入疗养院）：")
        if not ok or not name.strip():
            return
        name = name.strip()
        self._initial_state.set_flag(name, True)
        self._refresh_initial_state_editor()
        self.data_changed.emit()

    def _edit_initial_flag(self, item: QListWidgetItem):
        key = item.data(Qt.UserRole)
        cur_val = self._initial_state.get_flag(key)
        items = ["✓ 已标记（True）", "✗ 未标记（False）"]
        choice, ok = QInputDialog.getItem(
            self, "编辑标记", f"选择标记「{key}」的值：",
            items, 0 if cur_val else 1, False
        )
        if ok:
            new_val = choice.startswith("✓")
            self._initial_state.set_flag(key, new_val)
            self._refresh_initial_state_editor()
            self.data_changed.emit()

    def _del_initial_flag(self):
        row = self.lst_initial_flags.currentRow()
        if row < 0:
            return
        key = self.lst_initial_flags.item(row).data(Qt.UserRole)
        del self._initial_state.flags[key]
        self._refresh_initial_state_editor()
        self.data_changed.emit()

    def _add_initial_clue(self):
        name, ok = QInputDialog.getText(self, "添加初始线索", "线索ID（如 祭坛照片）：")
        if not ok or not name.strip():
            return
        name = name.strip()
        items = ["✓ 已获得（True）", "✗ 未获得（False）"]
        choice, ok2 = QInputDialog.getItem(
            self, "初始线索状态", f"选择线索「{name}」的初始状态：",
            items, 0, False
        )
        if ok2:
            val = choice.startswith("✓")
            self._initial_state.add_clue(name, val)
            self._refresh_initial_state_editor()
            self.data_changed.emit()

    def _edit_initial_clue(self, item: QListWidgetItem):
        key = item.data(Qt.UserRole)
        cur_val = self._initial_state.has_clue(key)
        items = ["✓ 已获得（True）", "✗ 未获得（False）"]
        choice, ok = QInputDialog.getItem(
            self, "编辑线索", f"选择线索「{key}」的状态：",
            items, 0 if cur_val else 1, False
        )
        if ok:
            new_val = choice.startswith("✓")
            self._initial_state.add_clue(key, new_val)
            self._refresh_initial_state_editor()
            self.data_changed.emit()

    def _del_initial_clue(self):
        row = self.lst_initial_clues.currentRow()
        if row < 0:
            return
        key = self.lst_initial_clues.item(row).data(Qt.UserRole)
        del self._initial_state.clues[key]
        self._refresh_initial_state_editor()
        self.data_changed.emit()

    def _add_initial_character(self):
        name, ok = QInputDialog.getText(self, "添加初始角色", "角色ID（如 护士_林）：")
        if not ok or not name.strip():
            return
        name = name.strip()
        items = ["存活", "死亡", "失踪", "发疯"]
        choice, ok2 = QInputDialog.getItem(
            self, "角色初始状态", f"选择角色「{name}」的初始状态：",
            items, 0, False
        )
        if ok2:
            from models import CharacterStatus
            status_map = {"存活": CharacterStatus.ALIVE, "死亡": CharacterStatus.DEAD,
                         "失踪": CharacterStatus.MISSING, "发疯": CharacterStatus.INSANE}
            self._initial_state.set_character_status(name, status_map[choice])
            self._refresh_initial_state_editor()
            self.data_changed.emit()

    def _edit_initial_char(self, item: QListWidgetItem):
        from models import CharacterStatus
        key = item.data(Qt.UserRole)
        cur_val = self._initial_state.get_character_status(key)
        items = ["存活", "死亡", "失踪", "发疯"]
        status_map = {"存活": CharacterStatus.ALIVE, "死亡": CharacterStatus.DEAD,
                     "失踪": CharacterStatus.MISSING, "发疯": CharacterStatus.INSANE}
        rev_map = {v: k for k, v in status_map.items()}
        cur_idx = items.index(rev_map.get(cur_val, "存活"))
        choice, ok = QInputDialog.getItem(
            self, "编辑角色状态", f"选择角色「{key}」的状态：",
            items, cur_idx, False
        )
        if ok:
            self._initial_state.set_character_status(key, status_map[choice])
            self._refresh_initial_state_editor()
            self.data_changed.emit()

    def _del_initial_char(self):
        row = self.lst_initial_chars.currentRow()
        if row < 0:
            return
        key = self.lst_initial_chars.item(row).data(Qt.UserRole)
        del self._initial_state.characters[key]
        self._refresh_initial_state_editor()
        self.data_changed.emit()

    def _build_event_editor(self):
        gb_base = QGroupBox("📝 事件基本信息")
        form = QFormLayout(gb_base)
        self.ed_title = QLineEdit()
        self.ed_title.textChanged.connect(self._on_title_change)
        self.sp_chapter = QSpinBox()
        self.sp_chapter.setRange(1, 50)
        self.sp_chapter.valueChanged.connect(self._on_chapter_change)
        self.sp_order = QSpinBox()
        self.sp_order.setRange(0, 1000)
        self.sp_order.valueChanged.connect(self._on_order_change)
        self.ed_desc = QTextEdit()
        self.ed_desc.setFixedHeight(80)
        self.ed_desc.textChanged.connect(self._on_desc_change)
        form.addRow("标题：", self.ed_title)
        row_ch = QHBoxLayout()
        row_ch.addWidget(self.sp_chapter)
        row_ch.addWidget(QLabel("同章节顺序："))
        row_ch.addWidget(self.sp_order)
        row_ch.addStretch()
        form.addRow("章节：", row_ch)
        form.addRow("事件描述：", self.ed_desc)
        self.right_layout.addWidget(gb_base)

        gb_cond = QGroupBox("🔒 触发前置条件（所有条件满足才会触发该事件，可留空）")
        v = QVBoxLayout(gb_cond)
        self.lst_conditions = QListWidget()
        self.lst_conditions.itemDoubleClicked.connect(self._edit_condition)
        v.addWidget(self.lst_conditions)
        b = QHBoxLayout()
        btn_c_add = QPushButton("+ 新增条件")
        btn_c_add.clicked.connect(self._add_condition)
        btn_c_edit = QPushButton("编辑选中")
        btn_c_edit.clicked.connect(self._edit_condition)
        btn_c_del = QPushButton("删除选中")
        btn_c_del.setProperty("danger", True)
        btn_c_del.clicked.connect(self._del_condition)
        b.addWidget(btn_c_add)
        b.addWidget(btn_c_edit)
        b.addWidget(btn_c_del)
        v.addLayout(b)
        self.right_layout.addWidget(gb_cond)

        gb_choice = QGroupBox("🎮 玩家选择与影响")
        v2 = QVBoxLayout(gb_choice)
        self.lst_choices = QListWidget()
        self.lst_choices.itemSelectionChanged.connect(self._on_select_choice)
        v2.addWidget(self.lst_choices, 1)
        bc = QHBoxLayout()
        btn_ch_add = QPushButton("+ 新增选项")
        btn_ch_add.clicked.connect(self._add_choice)
        btn_ch_del = QPushButton("删除选项")
        btn_ch_del.setProperty("danger", True)
        btn_ch_del.clicked.connect(self._del_choice)
        bc.addWidget(btn_ch_add)
        bc.addWidget(btn_ch_del)
        v2.addLayout(bc)

        self.ed_choice_text = QLineEdit()
        self.ed_choice_text.setPlaceholderText("选中上方选项后，可在此编辑选项文本...")
        self.ed_choice_text.textChanged.connect(self._on_choice_text_change)
        v2.addWidget(QLabel("当前选项文本："))
        v2.addWidget(self.ed_choice_text)

        v2.addWidget(QLabel("📊 选择后效果（影响恐惧值/线索/角色/标记）："))
        self.lst_effects = QListWidget()
        self.lst_effects.itemDoubleClicked.connect(self._edit_effect)
        v2.addWidget(self.lst_effects, 1)
        be = QHBoxLayout()
        btn_e_add = QPushButton("+ 新增效果")
        btn_e_add.clicked.connect(self._add_effect)
        btn_e_edit = QPushButton("编辑选中")
        btn_e_edit.clicked.connect(self._edit_effect)
        btn_e_del = QPushButton("删除效果")
        btn_e_del.setProperty("danger", True)
        btn_e_del.clicked.connect(self._del_effect)
        be.addWidget(btn_e_add)
        be.addWidget(btn_e_edit)
        be.addWidget(btn_e_del)
        v2.addLayout(be)

        self.right_layout.addWidget(gb_choice, 1)
        self._set_editor_enabled(False)

    def _set_editor_enabled(self, enabled: bool):
        for w in [
            self.ed_title, self.sp_chapter, self.sp_order, self.ed_desc,
        ]:
            w.setEnabled(enabled)

    def set_data(self, events: List[Event], endings: List[Ending], initial_state: Optional[GameState] = None):
        self._events = events
        self._endings = endings
        if initial_state is not None:
            self._initial_state = initial_state
        self._current_event = None
        self._refresh_event_tree()
        self._refresh_initial_state_editor()

    def get_events(self) -> List[Event]:
        return self._events

    def get_initial_state(self) -> GameState:
        return self._initial_state

    def _refresh_event_tree(self):
        self.tree_events.clear()
        chapters: dict[int, QTreeWidgetItem] = {}
        sorted_events = sorted(self._events, key=lambda e: (e.chapter, e.order))
        for ev in sorted_events:
            if ev.chapter not in chapters:
                ch_item = QTreeWidgetItem([f"第 {ev.chapter} 章", str(ev.chapter)])
                ch_item.setData(0, Qt.UserRole, None)
                ch_item.setForeground(0, QBrush(COLOR_INFO))
                font = QFont()
                font.setBold(True)
                ch_item.setFont(0, font)
                chapters[ev.chapter] = ch_item
                self.tree_events.addTopLevelItem(ch_item)
            ev_item = QTreeWidgetItem([ev.title or "(未命名)", str(ev.chapter)])
            ev_item.setData(0, Qt.UserRole, ev.id)
            ev_item.setForeground(1, QBrush(COLOR_INFO))
            chapters[ev.chapter].addChild(ev_item)
        self.tree_events.expandAll()
        total = len(self._events)
        chs = len(chapters)
        self.lbl_count.setText(f"共 {chs} 章 / {total} 个事件")

    def _on_select_event(self):
        items = self.tree_events.selectedItems()
        if not items:
            return
        ev_id = items[0].data(0, Qt.UserRole)
        if ev_id is None:
            self._current_event = None
            self._set_editor_enabled(False)
            return
        ev = next((e for e in self._events if e.id == ev_id), None)
        if ev is None:
            return
        self._current_event = ev
        self._set_editor_enabled(True)
        self._load_event_to_editor(ev)

    def _load_event_to_editor(self, ev: Event):
        self.ed_title.blockSignals(True)
        self.sp_chapter.blockSignals(True)
        self.sp_order.blockSignals(True)
        self.ed_desc.blockSignals(True)
        self.ed_title.setText(ev.title)
        self.sp_chapter.setValue(ev.chapter)
        self.sp_order.setValue(ev.order)
        self.ed_desc.setPlainText(ev.description)
        self.ed_title.blockSignals(False)
        self.sp_chapter.blockSignals(False)
        self.sp_order.blockSignals(False)
        self.ed_desc.blockSignals(False)

        self.lst_conditions.clear()
        for c in ev.conditions:
            item = QListWidgetItem(c.human_readable())
            item.setData(Qt.UserRole, c.id)
            item.setForeground(QBrush(COLOR_INFO))
            self.lst_conditions.addItem(item)

        self.lst_choices.clear()
        for ch in ev.choices:
            label = ch.text or "(未命名选项)"
            item = QListWidgetItem(f"🔘 {label}   （{len(ch.effects)} 个效果）")
            item.setData(Qt.UserRole, ch.id)
            self.lst_choices.addItem(item)

        self._selected_choice_id = None
        self.ed_choice_text.clear()
        self.lst_effects.clear()

    def _on_title_change(self):
        if self._current_event and self.ed_title.isEnabled():
            self._current_event.title = self.ed_title.text()
            self._refresh_tree_current()
            self.data_changed.emit()

    def _on_chapter_change(self):
        if self._current_event and self.sp_chapter.isEnabled():
            self._current_event.chapter = self.sp_chapter.value()
            self._refresh_event_tree()
            self.data_changed.emit()

    def _on_order_change(self):
        if self._current_event and self.sp_order.isEnabled():
            self._current_event.order = self.sp_order.value()
            self._refresh_event_tree()
            self.data_changed.emit()

    def _on_desc_change(self):
        if self._current_event and self.ed_desc.isEnabled():
            self._current_event.description = self.ed_desc.toPlainText()
            self.data_changed.emit()

    def _refresh_tree_current(self):
        if not self._current_event:
            return
        items = self.tree_events.selectedItems()
        if items:
            items[0].setText(0, self._current_event.title or "(未命名)")
            items[0].setText(1, str(self._current_event.chapter))

    def _add_chapter_dialog(self):
        chapters = sorted({e.chapter for e in self._events})
        default = (chapters[-1] + 1) if chapters else 1
        ch, ok = QInputDialog.getInt(self, "新增章节", "章节号：", default, 1, 50)
        if not ok:
            return
        title, ok2 = QInputDialog.getText(self, "章节说明", "（可选）输入该章节第一个事件标题：", text=f"第{ch}章事件")
        if not ok2:
            title = f"第{ch}章事件"
        ev = Event(title=title or "(未命名)", chapter=ch, order=0, description="")
        self._events.append(ev)
        self._refresh_event_tree()
        self.data_changed.emit()

    def _add_event(self):
        if not self._events:
            default_chapter = 1
            default_order = 0
        else:
            last = sorted(self._events, key=lambda e: (e.chapter, e.order))[-1]
            default_chapter = last.chapter
            default_order = last.order + 1
        ev = Event(
            title="新事件",
            chapter=default_chapter,
            order=default_order,
            description="",
        )
        self._events.append(ev)
        self._refresh_event_tree()
        self.data_changed.emit()

    def _delete_selected(self):
        items = self.tree_events.selectedItems()
        if not items:
            return
        ev_id = items[0].data(0, Qt.UserRole)
        if ev_id is None:
            return
        ev = next((e for e in self._events if e.id == ev_id), None)
        if ev is None:
            return
        r = QMessageBox.question(
            self, "确认删除", f"确定删除事件「{ev.title}」吗？此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if r == QMessageBox.Yes:
            self._events.remove(ev)
            self._current_event = None
            self._set_editor_enabled(False)
            self._refresh_event_tree()
            self.data_changed.emit()

    def _add_condition(self):
        if not self._current_event:
            return
        dlg = ConditionEditDialog(parent=self)
        if dlg.exec() == dlg.Accepted:
            c = dlg.get_condition()
            self._current_event.conditions.append(c)
            self._load_event_to_editor(self._current_event)
            self.data_changed.emit()

    def _edit_condition(self):
        if not self._current_event:
            return
        row = self.lst_conditions.currentRow()
        if row < 0 or row >= len(self._current_event.conditions):
            return
        dlg = ConditionEditDialog(self._current_event.conditions[row], self)
        if dlg.exec() == dlg.Accepted:
            self._current_event.conditions[row] = dlg.get_condition()
            self._load_event_to_editor(self._current_event)
            self.data_changed.emit()

    def _del_condition(self):
        if not self._current_event:
            return
        row = self.lst_conditions.currentRow()
        if row < 0 or row >= len(self._current_event.conditions):
            return
        del self._current_event.conditions[row]
        self._load_event_to_editor(self._current_event)
        self.data_changed.emit()

    def _add_choice(self):
        if not self._current_event:
            return
        ch = Choice(text=f"选项 {len(self._current_event.choices) + 1}")
        self._current_event.choices.append(ch)
        self._load_event_to_editor(self._current_event)
        self.data_changed.emit()

    def _del_choice(self):
        if not self._current_event:
            return
        row = self.lst_choices.currentRow()
        if row < 0 or row >= len(self._current_event.choices):
            return
        del self._current_event.choices[row]
        self._load_event_to_editor(self._current_event)
        self.data_changed.emit()

    def _on_select_choice(self):
        if not self._current_event:
            return
        row = self.lst_choices.currentRow()
        self.lst_effects.clear()
        self.ed_choice_text.blockSignals(True)
        if row < 0 or row >= len(self._current_event.choices):
            self._selected_choice_id = None
            self.ed_choice_text.clear()
        else:
            ch = self._current_event.choices[row]
            self._selected_choice_id = ch.id
            self.ed_choice_text.setText(ch.text)
            for e in ch.effects:
                item = QListWidgetItem(e.human_readable())
                item.setData(Qt.UserRole, e.id)
                val = e.value or 0
                if e.effect_type == ChoiceEffectType.ADD_FEAR:
                    color = COLOR_BROKEN if val > 0 else COLOR_VALID
                elif e.effect_type in (ChoiceEffectType.SET_CHAR_DEAD, ChoiceEffectType.SET_CHAR_MISSING, ChoiceEffectType.SET_CHAR_INSANE):
                    color = COLOR_BROKEN
                else:
                    color = COLOR_VALID
                item.setForeground(QBrush(color))
                self.lst_effects.addItem(item)
        self.ed_choice_text.blockSignals(False)

    def _on_choice_text_change(self):
        if not self._current_event or not getattr(self, "_selected_choice_id", None):
            return
        ch = next(
            (c for c in self._current_event.choices if c.id == self._selected_choice_id),
            None,
        )
        if ch:
            ch.text = self.ed_choice_text.text()
            self._reload_choices()
            self.data_changed.emit()

    def _reload_choices(self):
        cur_row = self.lst_choices.currentRow()
        self.lst_choices.clear()
        if not self._current_event:
            return
        for ch in self._current_event.choices:
            label = ch.text or "(未命名选项)"
            item = QListWidgetItem(f"🔘 {label}   （{len(ch.effects)} 个效果）")
            item.setData(Qt.UserRole, ch.id)
            self.lst_choices.addItem(item)
        if 0 <= cur_row < self.lst_choices.count():
            self.lst_choices.setCurrentRow(cur_row)

    def _current_choice(self) -> Optional[Choice]:
        if not self._current_event or not getattr(self, "_selected_choice_id", None):
            return None
        return next(
            (c for c in self._current_event.choices if c.id == self._selected_choice_id),
            None,
        )

    def _add_effect(self):
        ch = self._current_choice()
        if not ch:
            QMessageBox.information(self, "提示", "请先选择一个选项。")
            return
        dlg = EffectEditDialog(parent=self)
        if dlg.exec() == dlg.Accepted:
            ch.effects.append(dlg.get_effect())
            self._on_select_choice()
            self._reload_choices()
            self.data_changed.emit()

    def _edit_effect(self):
        ch = self._current_choice()
        if not ch:
            return
        row = self.lst_effects.currentRow()
        if row < 0 or row >= len(ch.effects):
            return
        dlg = EffectEditDialog(ch.effects[row], self)
        if dlg.exec() == dlg.Accepted:
            ch.effects[row] = dlg.get_effect()
            self._on_select_choice()
            self._reload_choices()
            self.data_changed.emit()

    def _del_effect(self):
        ch = self._current_choice()
        if not ch:
            return
        row = self.lst_effects.currentRow()
        if row < 0 or row >= len(ch.effects):
            return
        del ch.effects[row]
        self._on_select_choice()
        self._reload_choices()
        self.data_changed.emit()
