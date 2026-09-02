import os
from copy import deepcopy


FILM_SPACE_ENV = "ACU_FILM_LEARNING_SPACE_ID"
FILM_MAX_SKILL_WRITES = 3
FILM_MAX_NEW_SKILLS = 1
FILM_REFERENCE_IMAGE_URL = (
    "https://upload.wikimedia.org/wikipedia/commons/d/d4/"
    "The_Cabinet_of_Dr_Caligari_Holstenwall.jpg"
)
FILM_REFERENCE_SOURCE_URL = (
    "https://commons.wikimedia.org/wiki/"
    "File:The_Cabinet_of_Dr_Caligari_Holstenwall.jpg"
)

LANGUAGE_POLICY = (
    "使用用户的主要语言生成蒸馏结果以及所有已学习的偏好描述和正文。"
    "保留代码、机器可读标识符和工具名称。"
)

ACU_TASK_POLICY = """

## ACU 偏好学习
当输入包含 `learning_trigger: user_dissatisfaction` 时，表示用户已经从
使用体验角度拒绝、纠正或改变了之前的方向。

- 不要等待任务在技术上完成后再记录这个学习信号。
- 将带有该信号的 pending 或 running task 视为需要学习的 Experience。关联
  相关消息，记录用户在当前语境中的纠正，并交给 ACU adapter 进行偏好蒸馏。
- 一句含义不明确的话不足以支持长期偏好。优先依据用户目标、当前阶段、
  取舍、被拒绝的方向和拒绝原因。
- 不要把这个信号转化为通用技术 SOP。
"""

ACU_DISTILLATION_POLICY = """

## ACU 轨迹偏好蒸馏
当输入包含 `learning_trigger: user_dissatisfaction` 时，提炼用户体验上的
方向差异。

在证据支持时识别：
- 用户目标、当前阶段和具体情境；
- Agent 采取了什么方向，用户希望改成什么方向；
- 当前情境暴露出的用户特征或偏好；
- 用户选择某个方向而不是另一个方向的原因；
- 未来遇到相似轨迹时应召回的可泛化规则。

可复用的抽象形式是：
`情境 -> 用户偏好或特征 -> 原因或取舍 -> 可复用提醒`。
不要从单一事实过度泛化，也不要把结果写成任务日志。
在蒸馏结果中保留学习信号中的完整 `experience_id`，优先放入
`applies_when`，以便 Skill Agent 保留证据关联。
证据不足以支持可复用偏好时，跳过学习。
"""

ACU_SKILL_POLICY = """

## ACU 偏好文档
对于 ACU 不满意语境，学习得到的 Skill 是简洁的用户偏好文档。

每份偏好文档不得超过 1500 个字符，并包含：

```markdown
---
name: "preference-title"
description: "偏好的简短描述。"
type: user_preference
experience_id: exp-...
related_experience_ids:
  - exp-...
---

# 偏好标题

## 描述
偏好的简短描述。

## 原因
当前情境、用户特征或偏好，以及做出选择的原因。

## Advisor guidance
出现相似轨迹时使用的简短提醒。
```

对于 ACU 不满意语境，每条不同的可复用偏好都应作为独立的顶层 Skill 保存。
不要写入 Acontext 内置的 `daily-logs` 或 `user-general-facts` Skill，也不要
使用这些通用 Skill 作为 ACU 偏好的目录标题。创建或更新一个 name 和
description 直接描述该偏好的专用 Skill，并将上述偏好文档写入它的
`SKILL.md`。

创建或更新文档前，先检查相关的已有 Skill。将整个 Learning Space 视为一份
持续演进的用户偏好集合：

- 优先更新相关偏好，避免创建重复 Skill。
- 从情境和原因中归纳，不要从一次性的实现动作中归纳。
- 偏好冲突时，先判断它们是否分别适用于不同目标、阶段、风险等级或语境；
  条件可以区分时，将条件合并到一份连贯的偏好中。
- 用户确实改变偏好时，修订旧文档，不要追加相互矛盾的条目。只保留少量
  相关的 Experience ID。
- 清理过期或重复内容，同时保持文档不超过字符限制。
- 没有证据时不要推断人格特征，也不要创建独立的 profile 数据库。
"""

FILM_TASK_PROMPT = """你是影视团队 Learning Space 中的 Acontext 任务整理 Agent。
只有当前会话绑定到已配置的影视 Learning Space 时才使用这份提示词。

当前会话包含一条完整的影视 SelectionExperience。它可以是纯文字，也可以
是一条绑定一张或多张图片的文字消息。为后续蒸馏保留原始消息及其图片绑定。

## 工作流程
- 无论其中涉及多少视听语言主题，都将一条 SelectionExperience 作为一个学习单元。
- 为这条 Experience 创建或更新一个 task。
- 将原始消息关联到该 task。
- 不要把光影、色彩、构图、摄影机或其他主题拆成多个 task。
- 不要调用 `submit_user_preference`，也不要使用 planning section。
- 将证据交给现有学习队列，并结束本轮任务整理，不要提出问题。

Experience 文字是权威学习输入。不要用任务摘要替换它，也不要在任务跟踪阶段
提前推断偏好。后续影视蒸馏和 Skill Learner 阶段会保留条件化规则，并可以
从同一条 Experience 更新多个主题 Skill。
"""

FILM_DISTILLATION_PROMPT = """你是影视团队的视听语言蒸馏 Agent。当前学习会话属于
已配置的影视 Learning Space，并包含一条 SelectionExperience。

分析完整的关联证据。文字可能包含 quality_context、固定范式的影视语言分析、
团队决定、good_points、missing_points、rejection_reason、来源信息，以及与同一
条消息绑定的一张或多张图片。

先从 Experience 中识别表达目标：希望观众感受到什么、理解什么，或如何感知人物
与环境的关系。再把画面中的具体手段归纳为可迁移的导演语言原则，形成：

表达目标 → 导演语言原则 → 可用于生图的视听实现

从这条 Experience 中提取所有有证据支持的学习点，并且只调用一次
`report_film_learning_claims`。每条 claim 必须包含 `topic`、`applies_when`、
`prefer`、`avoid`、`why` 和 `example_ref`。

`applies_when` 以表达目标、观众感受、人物关系或叙事功能为中心，避免写成单一
地点、动作或剧情事件。`prefer` 描述可执行的视听语言选择，`why` 描述它如何
服务表达目标和后续生图质量。具体作品、人物、地点和镜头只作为证据保留在
`evidence_summary`、`example_ref` 和 Experience 中。

相同视听手段在不同表达目标下可能对应不同规则；应保留这些条件化差异，并从
优点、欠缺和淘汰原因中提取可复用的方向。不要根据颜色、构图或镜头手段的出现
频率生成无条件规则，也不要把单一案例的剧情背景直接写成通用规律。

学习结果可以覆盖 narrative context、character and relationship、lighting、
color、shot and composition、camera、mise-en-scene、visual emotion 和
integrated visual language 等主题。使用用户的主要语言，不创建任务日志或通用
用户画像。
"""

FILM_SKILL_LEARNER_PROMPT = """你是影视团队的 Quality Skill Learner。当前学习会话
属于已配置的影视 Learning Space。根据蒸馏结果更新影视主题级 Quality Skill。

输入中的 Available Skills 是当前 Learning Space 实时提供的 Skill catalog，
每一项包含 Skill 的准确 `name`（标题）和 `description`。先根据这份 catalog
判断归属，调用工具时使用 catalog 中的准确 Skill name；不要使用提示词中预设的 Skill 名称或固定主题目录。

从当前 catalog 中选择与本条蒸馏结果最相关的 Skill，最多实际更新 3 个。优先
复用已有 Skill；只有当前 catalog 没有能够承载该学习点的 Skill 时，才创建新的
Quality Skill，单次 Learner 运行最多创建 1 个新 Skill。不要编辑或创建
`daily-logs`、`user-general-facts` 等通用系统 Skill。

编辑 Skill 前先读取该 Skill 的 `SKILL.md`。多个 LearningClaim 如果服务于
同一个剧本语境、人物目标或叙事目的，应先合并为一组条件化规则，再写入最相关
的 1-3 个 Skill。单次 Learner 运行的写入范围最多为 3 个 Skill；不要为了覆盖
每个 Claim 的 topic 而逐个创建或修改 Skill。完成相关写入后立即结束本轮。

Skill 的标题描述可迁移的导演语言原则，description 概括表达目标与主要视听方法。
正文保留以下结构：

## Applies When
表达目标、观众感受、人物关系、叙事功能和必要的制作条件。

## Prefer
服务上述表达目标的条件化视听语言选择，以及可用于生图的执行方向。

## Avoid
需要避免的条件化选择，包括提交内容中的欠缺和淘汰原因。

## Why
这些选择如何服务叙事含义和生图质量。

## Examples
简短的来源 Experience 引用。

同一 Skill 内可以保留多个表达目标不同的条件化规则。合并兼容证据时不要将
它们变成频率统计，也不要把具体地点或一次性剧情事件写成 Skill 的适用条件。
使用用户的主要语言，并保留机器可读标识符。只根据当前 Experience 和已有
Skill 的内容做必要修改。
"""

ACCOUNT_EXAMPLE_MATERIAL = {
    "text": (
        "用户希望把登录页改成更紧凑的工作界面。Agent 第一次提交了一个大幅营销式布局，"
        "用户回复：请收敛，不要增加与当前任务无关的装饰，只保留可直接操作的内容。"
    )
}

ACCOUNT_PROMPT_EXAMPLES = {
    "task": [
        {
            "id": "account-task-fixture-01",
            "title": "一次中文返工反馈",
            "origin": "reference_fixture",
            "material": ACCOUNT_EXAMPLE_MATERIAL,
            "artifact": {
                "format": "json",
                "content": {
                    "task_goal": "将页面收敛为可直接操作的紧凑工作界面",
                    "status": "pending",
                    "source_experience": "account-fixture-01",
                },
            },
        }
    ],
    "distillation": [
        {
            "id": "account-distillation-fixture-01",
            "title": "从返工反馈提取条件化偏好",
            "origin": "reference_fixture",
            "material": {
                **ACCOUNT_EXAMPLE_MATERIAL,
                "json": {
                    "experience_id": "account-fixture-01",
                    "quality_context": "产品界面设计与实现阶段",
                    "feedback_reason": "用户要求收敛并删除无关装饰",
                },
            },
            "artifact": {
                "format": "json",
                "content": {
                    "experience_id": "account-fixture-01",
                    "preference_candidates": [
                        {
                            "applies_when": "面对以操作效率为目标的产品界面任务",
                            "prefer": "紧凑、直接、可扫描的工作界面",
                            "avoid": "营销式首屏和与任务无关的装饰",
                        }
                    ],
                },
            },
        }
    ],
    "skill_learner": [
        {
            "id": "account-skill-learner-fixture-01",
            "title": "更新账户偏好文档",
            "origin": "reference_fixture",
            "material": {
                "json": {
                    "experience_id": "account-fixture-01",
                    "preference_candidates": [
                        {
                            "applies_when": "操作效率优先的产品界面任务",
                            "prefer": "紧凑、直接、可扫描",
                            "avoid": "营销式装饰",
                        }
                    ],
                },
                "text": "修改前 Skill：尚无相关界面密度偏好。",
            },
            "artifact": {
                "format": "markdown",
                "content": (
                    "# 紧凑的工作界面\n\n"
                    "## Applies When\n"
                    "面对以操作效率为目标的产品界面任务。\n\n"
                    "## Prefer\n"
                    "紧凑、直接、可扫描的工作界面。\n\n"
                    "## Avoid\n"
                    "营销式首屏和与任务无关的装饰。\n"
                ),
            },
        }
    ],
}

FILM_REFERENCE_MATERIAL = {
    "text": (
        "这张参考图用于表达陌生感、疏离感和主观距离的分镜。剧本语境：人物与环境"
        "尚未建立信任，叙事目标是在没有对白的情况下让观众先感到感知距离，再进入"
        "人物视角。"
    ),
    "json": {
        "experience_id": "film-fixture-caligari-holstenwall-01",
        "quality_context": (
            "表达目标是传达陌生感、疏离感和主观距离，让观众感知人物与环境之间的"
            "距离。生成分镜图需要保持明确的视觉层级，避免无方向的视觉噪声。"
        ),
        "film_language_analysis": {
            "narrative_context": {
                "function": "建立人物即将进入的异化城市环境",
                "emotion": "压迫、不安、疏离",
            },
            "lighting": {
                "direction": "大面积背光与局部轮廓光",
                "contrast": "明暗反差强",
                "shadow": "边缘和底部保留深色阴影",
            },
            "color": {
                "palette": "暗青黑与偏黄高光",
                "saturation": "整体低饱和，暖色区域集中在空间中心",
            },
            "shot_and_composition": {
                "scale": "远景",
                "composition": "中心轴线指向尖塔，四周建筑形成挤压",
                "negative_space": "顶部和边缘的暗部包围主体空间",
            },
            "mise_en_scene": {
                "space": "倾斜、密集、非现实的城市建筑",
                "visual_hierarchy": "尖塔作为视觉锚点，重复屋顶制造不稳定节奏",
            },
        },
        "team_decision": "reference",
        "good_points": [
            "建筑轮廓直接传达异化和压迫",
            "中心尖塔建立清晰视觉锚点",
            "暗部边界把观众视线收束到城市内部",
        ],
        "missing_points": [
            "若用于人物入场，后续镜头需要补充人物尺度对照",
        ],
        "rejection_reason": None,
        "source": {
            "work": "The Cabinet of Dr. Caligari",
            "fragment": "Holstenwall establishing image",
            "source_url": FILM_REFERENCE_SOURCE_URL,
        },
        "provenance": {
            "analysis_version": "film-json-v1",
            "license": "Public domain",
        },
    },
    "images": [
        {
            "url": FILM_REFERENCE_IMAGE_URL,
            "mimeType": "image/jpeg",
            "alt": "《卡里加利博士的小屋》中的 Holstenwall 城市场景参考图",
        }
    ],
}

FILM_REFERENCE_CLAIMS = [
    {
        "topic": "lighting",
        "applies_when": "表达陌生感、疏离感和主观距离，让观众先感到感知上的不安时",
        "prefer": "保留受控的明暗分区，以深边缘阴影和局部轮廓光限制环境信息",
        "avoid": "均匀铺开的无方向软光，使所有空间信息同等清晰",
        "why": "让信息的不完整成为人物与环境之间的感知距离",
        "example_ref": "film-fixture-caligari-holstenwall-01",
    },
    {
        "topic": "shot_and_composition",
        "applies_when": "需要让观众感到人物与环境存在距离，且环境先于人物建立心理压力时",
        "prefer": "使用明确视觉锚点、非均匀透视和向内收束的轮廓组织空间",
        "avoid": "平均分配视觉重量、缺少视线方向的平直构图",
        "why": "让空间关系先于剧情信息影响观众的身体感受",
        "example_ref": "film-fixture-caligari-holstenwall-01",
    },
    {
        "topic": "color",
        "applies_when": "表达陌生感、疏离感和第一视角感知时",
        "prefer": "采用较为单调、受控的色调，把有限的色彩变化留给叙事焦点",
        "avoid": "均匀丰富但缺乏叙事指向的综合色彩",
        "why": "减少视觉噪声，保持主观感知的一致性，让陌生感来自感知距离",
        "example_ref": "film-fixture-caligari-holstenwall-01",
    },
]

FILM_PROMPT_EXAMPLES = {
    "task": [
        {
            "id": "film-task-fixture-caligari-01",
            "title": "异化城市建立镜头",
            "origin": "reference_fixture",
            "material": FILM_REFERENCE_MATERIAL,
            "artifact": {
                "format": "json",
                "content": {
                    "task_goal": "整理一条影视 SelectionExperience 并交给后续蒸馏",
                    "learning_unit": "film-fixture-caligari-holstenwall-01",
                    "image_count": 1,
                },
            },
            "sourceUrl": FILM_REFERENCE_SOURCE_URL,
        }
    ],
    "distillation": [
        {
            "id": "film-distillation-fixture-caligari-01",
            "title": "从城市场景提取多个视听语言学习点",
            "origin": "reference_fixture",
            "material": FILM_REFERENCE_MATERIAL,
            "artifact": {
                "format": "json",
                "content": {
                    "experience_id": "film-fixture-caligari-holstenwall-01",
                    "evidence_summary": "异化城市通过尖锐建筑、中心尖塔、暗部包围和冷暖对照形成压迫感。",
                    "claims": FILM_REFERENCE_CLAIMS,
                },
            },
            "sourceUrl": FILM_REFERENCE_SOURCE_URL,
        }
    ],
    "skill_learner": [
        {
            "id": "film-skill-learner-fixture-caligari-01",
            "title": "更新影视主题 Quality Skill",
            "origin": "reference_fixture",
            "material": {
                "text": FILM_REFERENCE_MATERIAL["text"],
                "json": {
                    "experience_id": "film-fixture-caligari-holstenwall-01",
                    "claims": FILM_REFERENCE_CLAIMS,
                },
                "images": FILM_REFERENCE_MATERIAL["images"],
            },
            "artifact": {
                "format": "markdown",
                "content": (
                    "# 异化空间中的压迫性视觉语言\n\n"
                    "## Applies When\n"
                    "人物首次进入陌生城市，处于不安和疏离状态，需要先建立空间压迫。\n\n"
                    "## Prefer\n"
                    "使用远景、尖锐建筑轮廓、明确的中心视觉锚点、强反差和深边缘阴影；"
                    "以暗青黑为基础色，在叙事焦点处集中偏黄高光。\n\n"
                    "## Avoid\n"
                    "均匀软光、平直而平均的城市全景，以及全画面均匀高饱和的色彩。\n\n"
                    "## Why\n"
                    "空间秩序的不稳定先于人物进入观众感知，有限暖色负责引导视线并保留疏离感。\n\n"
                    "## Examples\n"
                    "film-fixture-caligari-holstenwall-01\n"
                ),
            },
            "sourceUrl": FILM_REFERENCE_SOURCE_URL,
        }
    ],
}

FILM_DISTILL_TOOL_FUNCTION = {
    "name": "report_film_learning_claims",
    "description": "报告一条 SelectionExperience 支持的全部条件化影视语言学习点。",
    "parameters": {
        "type": "object",
        "properties": {
            "experience_id": {"type": "string"},
            "evidence_summary": {"type": "string"},
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string"},
                        "applies_when": {"type": "string"},
                        "prefer": {"type": "string"},
                        "avoid": {"type": "string"},
                        "why": {"type": "string"},
                        "example_ref": {"type": "string"},
                    },
                    "required": [
                        "topic",
                        "applies_when",
                        "prefer",
                        "avoid",
                        "why",
                        "example_ref",
                    ],
                },
                "minItems": 1,
            },
        },
        "required": ["experience_id", "evidence_summary", "claims"],
    },
}


def film_space_id() -> str:
    return os.environ.get(FILM_SPACE_ENV, "").strip()


def is_film_space(learning_space_id: object) -> bool:
    configured = film_space_id()
    return bool(configured) and str(learning_space_id or "") == configured


def task_prompt_for_space(base_prompt: str, learning_space_id: object = None) -> str:
    if is_film_space(learning_space_id):
        return FILM_TASK_PROMPT
    return base_prompt + ACU_TASK_POLICY


def distillation_prompt_for_space(base_prompt: str, learning_space_id: object = None) -> str:
    if is_film_space(learning_space_id):
        return FILM_DISTILLATION_PROMPT
    return base_prompt + f"\n## Skill Language\n{LANGUAGE_POLICY}\n" + ACU_DISTILLATION_POLICY


def skill_learner_prompt_for_space(base_prompt: str, learning_space_id: object = None) -> str:
    if is_film_space(learning_space_id):
        return FILM_SKILL_LEARNER_PROMPT
    return base_prompt + f"\n## Skill Language\n{LANGUAGE_POLICY}\n" + ACU_SKILL_POLICY


def prompt_examples(
    stage: str, examples: dict[str, list[dict[str, object]]]
) -> list[dict[str, object]]:
    return deepcopy(examples.get(stage, []))


def film_prompt_cards() -> list[dict[str, object]]:
    return [
        {
            "id": "film-distillation",
            "stage": "distillation",
            "title": "影视视听语言蒸馏提示词",
            "description": "从一条图文 Experience 中提取多个条件化 LearningClaim。",
            "content": FILM_DISTILLATION_PROMPT,
            "language": "zh-CN",
            "source": "acu_learning_prompts.py: FILM_DISTILLATION_PROMPT",
            "execution": "used",
            "examples": prompt_examples("distillation", FILM_PROMPT_EXAMPLES),
        },
        {
            "id": "film-skill-learner",
            "stage": "skill_learner",
            "title": "影视 Quality Skill 学习提示词",
            "description": "根据蒸馏结果更新一个或多个影视主题 Quality Skill。",
            "content": FILM_SKILL_LEARNER_PROMPT,
            "language": "zh-CN",
            "source": "acu_learning_prompts.py: FILM_SKILL_LEARNER_PROMPT",
            "execution": "used",
            "examples": prompt_examples("skill_learner", FILM_PROMPT_EXAMPLES),
        },
    ]


def account_prompt_examples(stage: str) -> list[dict[str, object]]:
    return prompt_examples(stage, ACCOUNT_PROMPT_EXAMPLES)
