from typing import List, Tuple

from models import (
    Event, Ending, Condition, ConditionType, Choice, ChoiceEffect,
    ChoiceEffectType, GameState, CharacterStatus,
)


def create_sample_data() -> Tuple[List[Event], List[Ending], GameState]:
    initial = GameState(
        fear_level=10,
        clues={},
        characters={
            "护士_林": CharacterStatus.ALIVE,
            "老人_陈": CharacterStatus.ALIVE,
            "院长": CharacterStatus.ALIVE,
        },
        flags={"已入疗养院": True},
    )

    e1 = Event(
        title="抵达疗养院门口",
        chapter=1,
        order=0,
        description="主角在浓雾中来到疗养院门口，门口保安室空无一人。",
        conditions=[],
        choices=[
            Choice(
                text="按下门铃等待",
                effects=[
                    ChoiceEffect(ChoiceEffectType.ADD_FEAR, "", value=5, description="恐惧值 +5"),
                    ChoiceEffect(ChoiceEffectType.SET_FLAG, "按过门铃"),
                ],
            ),
            Choice(
                text="直接推门进入",
                effects=[
                    ChoiceEffect(ChoiceEffectType.ADD_FEAR, "", value=15, description="恐惧值 +15"),
                    ChoiceEffect(ChoiceEffectType.SET_FLAG, "强行闯入"),
                ],
            ),
        ],
    )

    e2 = Event(
        title="大厅遇到护士林",
        chapter=1,
        order=1,
        description="护士林从走廊走出来，笑容略显僵硬，递给主角一份登记文件。",
        conditions=[
            Condition(ConditionType.FLAG_TRUE, "已入疗养院"),
        ],
        choices=[
            Choice(
                text="相信她，如实填写并接受安排",
                effects=[
                    ChoiceEffect(ChoiceEffectType.SET_FLAG, "信任护士"),
                    ChoiceEffect(ChoiceEffectType.ADD_FEAR, "", value=3),
                ],
            ),
            Choice(
                text="假装填写，暗中观察",
                effects=[
                    ChoiceEffect(ChoiceEffectType.SET_FLAG, "警惕护士"),
                    ChoiceEffect(ChoiceEffectType.ADD_FEAR, "", value=8),
                    ChoiceEffect(ChoiceEffectType.SET_CLUE, "护士_手抖", description="获得线索：护士_手抖"),
                ],
            ),
        ],
    )

    e3 = Event(
        title="302房间的符咒",
        chapter=1,
        order=2,
        description="主角被安排到 302 房间，枕头下发现一张画满符文的黄纸符咒。",
        conditions=[
            Condition(ConditionType.FLAG_TRUE, "信任护士"),
        ],
        choices=[
            Choice(
                text="拿走符咒（藏进兜里）",
                effects=[
                    ChoiceEffect(ChoiceEffectType.SET_CLUE, "获得符咒", description="获得线索：获得符咒"),
                    ChoiceEffect(ChoiceEffectType.ADD_FEAR, "", value=10),
                    ChoiceEffect(ChoiceEffectType.SET_FLAG, "已拿符咒"),
                ],
            ),
            Choice(
                text="放回原处，不碰邪门东西",
                effects=[
                    ChoiceEffect(ChoiceEffectType.ADD_FEAR, "", value=2),
                ],
            ),
        ],
    )

    e4 = Event(
        title="走廊偶遇老人陈",
        chapter=2,
        order=0,
        description="深夜主角被走廊的异响吵醒，发现老人陈在走廊尽头对着墙低语。",
        conditions=[],
        choices=[
            Choice(
                text="上前搭话",
                effects=[
                    ChoiceEffect(ChoiceEffectType.SET_CLUE, "祭坛照片", description="获得线索：祭坛照片"),
                    ChoiceEffect(ChoiceEffectType.ADD_FEAR, "", value=12),
                    ChoiceEffect(ChoiceEffectType.SET_FLAG, "见过老人"),
                    ChoiceEffect(
                        ChoiceEffectType.ADD_FEAR, "", value=0,
                        description="老人偷偷塞给你一张祭坛照片"
                    ),
                ],
            ),
            Choice(
                text="躲起来偷听",
                effects=[
                    ChoiceEffect(ChoiceEffectType.SET_CLUE, "仪式_低语", description="获得线索：仪式_低语"),
                    ChoiceEffect(ChoiceEffectType.ADD_FEAR, "", value=18),
                    ChoiceEffect(ChoiceEffectType.SET_FLAG, "听过低语"),
                ],
            ),
            Choice(
                text="立刻回房锁门",
                effects=[
                    ChoiceEffect(ChoiceEffectType.ADD_FEAR, "", value=5),
                ],
            ),
        ],
    )

    e5 = Event(
        title="护士查房",
        chapter=2,
        order=1,
        description="护士林凌晨查房，神色紧张地检查了房间各个角落。",
        conditions=[
            Condition(ConditionType.FLAG_TRUE, "警惕护士"),
        ],
        choices=[
            Choice(
                text="假装睡着，看她要干什么",
                effects=[
                    ChoiceEffect(ChoiceEffectType.SET_CLUE, "护士找符咒", description="获得线索：护士找符咒"),
                    ChoiceEffect(ChoiceEffectType.ADD_FEAR, "", value=15),
                ],
            ),
            Choice(
                text="突然开灯质问她",
                effects=[
                    ChoiceEffect(ChoiceEffectType.ADD_FEAR, "", value=20),
                    ChoiceEffect(ChoiceEffectType.SET_FLAG, "与护士翻脸"),
                ],
            ),
        ],
    )

    e6 = Event(
        title="发现地下室入口",
        chapter=2,
        order=2,
        description="在厨房后面发现一扇锁着的铁门，似乎通往地下。",
        conditions=[
            Condition(ConditionType.HAS_CLUE, "仪式_低语"),
        ],
        choices=[
            Choice(
                text="用找到的钥匙打开地下室门",
                effects=[
                    ChoiceEffect(ChoiceEffectType.SET_FLAG, "进入地下室"),
                    ChoiceEffect(ChoiceEffectType.SET_CLUE, "地下室祭坛", description="获得线索：地下室祭坛"),
                    ChoiceEffect(ChoiceEffectType.ADD_FEAR, "", value=30),
                ],
            ),
            Choice(
                text="暂不打开，先收集更多信息",
                effects=[
                    ChoiceEffect(ChoiceEffectType.ADD_FEAR, "", value=5),
                ],
            ),
        ],
    )

    e7 = Event(
        title="地下室的真相",
        chapter=3,
        order=0,
        description="地下室深处是一个祭坛，上面摆放着失踪病人的遗物。",
        conditions=[
            Condition(ConditionType.FLAG_TRUE, "进入地下室"),
        ],
        choices=[
            Choice(
                text="拍照留证后离开",
                effects=[
                    ChoiceEffect(ChoiceEffectType.SET_CLUE, "取证完成", description="获得线索：取证完成"),
                    ChoiceEffect(ChoiceEffectType.ADD_FEAR, "", value=10),
                ],
            ),
            Choice(
                text="破坏祭坛上的法器",
                effects=[
                    ChoiceEffect(ChoiceEffectType.SET_FLAG, "破坏仪式"),
                    ChoiceEffect(ChoiceEffectType.ADD_FEAR, "", value=25),
                    ChoiceEffect(ChoiceEffectType.SET_CLUE, "院长现身", description="获得线索：院长现身"),
                    ChoiceEffect(ChoiceEffectType.SET_CHAR_DEAD, "老人_陈", description="老人_陈 死亡"),
                ],
            ),
        ],
    )

    e8 = Event(
        title="护士的真相",
        chapter=3,
        order=1,
        description="护士林在楼梯间拦住你，她的皮肤开始像纸一样剥落。",
        conditions=[
            Condition(ConditionType.FLAG_TRUE, "与护士翻脸"),
            Condition(ConditionType.HAS_CLUE, "护士找符咒"),
        ],
        choices=[
            Choice(
                text="举起符咒抵抗",
                effects=[
                    ChoiceEffect(ChoiceEffectType.SET_FLAG, "用符咒击退"),
                    ChoiceEffect(ChoiceEffectType.ADD_FEAR, "", value=20),
                    ChoiceEffect(ChoiceEffectType.SET_CHAR_DEAD, "护士_林", description="护士_林 死亡"),
                ],
            ),
            Choice(
                text="转身逃跑",
                effects=[
                    ChoiceEffect(ChoiceEffectType.ADD_FEAR, "", value=35),
                    ChoiceEffect(ChoiceEffectType.SET_FLAG, "被护士追击"),
                ],
            ),
        ],
    )

    e9 = Event(
        title="最终对峙：院长现身",
        chapter=3,
        order=2,
        description="院长带着一群阴影围住了你：「既然知道了，就别想活着出去。」",
        conditions=[
            Condition(ConditionType.FLAG_TRUE, "进入地下室"),
        ],
        choices=[
            Choice(
                text="拿出符咒 + 照片威胁报警",
                effects=[
                    ChoiceEffect(ChoiceEffectType.SET_FLAG, "谈判策略"),
                    ChoiceEffect(ChoiceEffectType.ADD_FEAR, "", value=10),
                ],
            ),
            Choice(
                text="趁乱冲出大门",
                effects=[
                    ChoiceEffect(ChoiceEffectType.ADD_FEAR, "", value=20),
                    ChoiceEffect(ChoiceEffectType.SET_FLAG, "强行逃离"),
                ],
            ),
        ],
    )

    events = [e1, e2, e3, e4, e5, e6, e7, e8, e9]

    ending_good = Ending(
        title="真相大白（良好结局）",
        description="主角凭借符咒与证据全身而退，疗养院的人体实验与邪教仪式被曝光。",
        conditions=[
            Condition(ConditionType.HAS_CLUE, "获得符咒", description="已获得符咒"),
            Condition(ConditionType.HAS_CLUE, "取证完成", description="完成取证"),
            Condition(ConditionType.HAS_CLUE, "祭坛照片", description="见过祭坛照片"),
            Condition(ConditionType.FEAR_LTE, "", threshold=65, description="恐惧值 ≤ 65"),
            Condition(ConditionType.CHAR_ALIVE, "老人_陈", description="老人_陈 存活"),
        ],
        dialogue_hints=[
            "主角：这张祭坛的照片和符咒就是铁证，警察马上就到。",
            "院长：不可能...你怎么会有祭坛照片？！",
        ],
    )

    ending_neutral = Ending(
        title="逃离疗养院（普通结局）",
        description="主角独自逃出，但没来得及揭发阴谋，疗养院仍在运作。",
        conditions=[
            Condition(ConditionType.FLAG_TRUE, "强行逃离"),
            Condition(ConditionType.FEAR_LTE, "", threshold=85),
        ],
        dialogue_hints=[
            "主角在浓雾中跑了不知多久才敢回头，疗养院的轮廓在雾中若隐若现...",
        ],
    )

    ending_bad_altar = Ending(
        title="成为祭品（坏结局·祭坛）",
        description="破坏仪式的代价，主角被院长拖上了祭坛。",
        conditions=[
            Condition(ConditionType.FLAG_TRUE, "破坏仪式"),
            Condition(ConditionType.NO_CLUE, "获得符咒", description="未获得符咒"),
            Condition(ConditionType.CHAR_DEAD, "老人_陈", description="老人_陈 死亡"),
        ],
        dialogue_hints=[
            "院长：敢破坏祭坛？下一个祭品就是你！",
            "主角眼前一黑，耳边只剩老人临终前的低语...",
        ],
    )

    ending_crazy = Ending(
        title="永远的病人（坏结局·疯狂）",
        description="恐惧值过高，主角被护士抓住后强行注射药物，永远成为疗养院的一员。",
        conditions=[
            Condition(ConditionType.FEAR_GTE, "", threshold=85, description="恐惧值 ≥ 85"),
            Condition(ConditionType.CHAR_ALIVE, "护士_林", description="护士_林 存活"),
            Condition(ConditionType.FLAG_TRUE, "被护士追击", description="被护士追击"),
        ],
        dialogue_hints=[
            "护士林：别怕，打了这针就不会再看见那些东西了。",
            "主角醒来时，自己已经穿着病号服躺在 302 房间...",
        ],
    )

    ending_hidden = Ending(
        title="驱邪者（隐藏真结局）",
        description="主角用符咒击退护士，救出老人，彻底揭穿并瓦解邪教。",
        conditions=[
            Condition(ConditionType.FLAG_TRUE, "用符咒击退"),
            Condition(ConditionType.HAS_CLUE, "获得符咒"),
            Condition(ConditionType.HAS_CLUE, "取证完成"),
            Condition(ConditionType.HAS_CLUE, "祭坛照片"),
            Condition(ConditionType.CHAR_ALIVE, "老人_陈"),
            Condition(ConditionType.CHAR_DEAD, "护士_林"),
            Condition(ConditionType.FLAG_TRUE, "见过老人"),
        ],
        dialogue_hints=[
            "老人陈：谢谢你...这张祭坛照片，就是我女儿留给我的...",
            "主角：一切都结束了，我会带你离开这里。",
        ],
    )

    endings = [ending_good, ending_neutral, ending_bad_altar, ending_crazy, ending_hidden]

    return events, endings, initial
