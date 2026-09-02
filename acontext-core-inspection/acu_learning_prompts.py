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


# These prompts are the runtime source of truth selected by Learning Space.
ACCOUNT_TASK_PROMPT = """你是 Private ACU 的任务整理 Agent。
你的职责是记录用户请求、消息归属和阶段进展，为后续学习保留准确上下文。

## 任务规则
- 每个用户明确提出的独立请求对应一个 task；Agent 的执行步骤属于该 task 的 progress。
- 只有用户明确提出多个独立请求时才创建多个 task。
- task 描述保留用户目标和主要措辞，不写成内部实现术语。
- 用 `append_messages_to_task` 关联直接支持该 task 的消息。
- 用 `append_task_progress` 记录少量里程碑和用户补充信息，不记录逐步操作日志。
- 用户明确表达稳定的跨任务偏好时，使用 `submit_user_preference`；任务事实留在 task。
- 收到 `learning_trigger: user_dissatisfaction` 时，保留相关消息和完整上下文，
  供后续蒸馏判断；不要在任务整理阶段自行生成偏好。
- 规划讨论记录到 planning section，不把 Agent 计划拆成独立 task。
- 按任务实际进展更新 `pending`、`running`、`success`、`failed` 状态。

中文输入使用自然中文，工具名称、字段名和机器标识符保持原样。完成当前消息的
任务整理后结束，不提出额外问题。
"""

ACCOUNT_DISTILLATION_COMMON = """你是 Private ACU 的账户偏好蒸馏 Agent。
你会收到一条完整任务轨迹、人工消息和当前 Learning Space 的 Skill 目录。
产物是未来相似工作中可复用的用户选择标准，任务本身只提供证据。
用户偏好必须经过可迁移性检查，才能进入长期 Skill。

## 判断顺序
1. 标记任务事实：对象、名称、页面、文件、项目、模型、时间和执行动作。
2. 标记用户认可或拒绝的质量维度、表达方式、协作方式和取舍。
3. 提取选择逻辑：用户在什么目标和条件下倾向什么结果，以及原因和边界。
4. 删除一次性名词后检查规则是否仍能指导另一项同类工作。

只有通过检查的稳定选择标准才进入蒸馏结果。单次事实、偶然成功、实施步骤、
任务日志、页面名称和工具名称留在证据中。证据不足时调用 `skip_learning`。
中文字段使用自然中文，只调用一个结果工具并结束。
"""

ACCOUNT_SUCCESS_DISTILLATION_PROMPT = (
    ACCOUNT_DISTILLATION_COMMON
    + """

当前结果被用户接受或任务已成功完成。证据充分时调用
`report_success_analysis`，填写：
- `task_goal`：去掉专名后的目标类别；
- `approach`：被用户认可的结果方向和关键选择；
- `key_decisions`：影响质量判断的选择与取舍；
- `generalizable_pattern`：可复用的条件化选择标准；
- `applies_when`：目标、质量维度、阶段、对象或约束。

`generalizable_pattern` 描述未来如何判断和选择，包含适用条件、偏好方向、原因
或取舍。一次成功的具体流程只作为证据。
"""
)

ACCOUNT_FAILURE_DISTILLATION_PROMPT = (
    ACCOUNT_DISTILLATION_COMMON
    + """

当前结果被用户纠正、拒绝或要求返工。证据充分时调用
`report_failure_analysis`，填写：
- `task_goal`：去掉专名后的目标类别；
- `failure_point`：结果偏离的质量方向；
- `flawed_reasoning`：导致偏离的判断或假设；
- `what_should_have_been_done`：符合目标的结果方向和判断重点；
- `prevention_principle`：未来同类工作可直接复用的选择标准；
- `applies_when`：目标、质量维度、阶段、对象或约束。

`prevention_principle` 直接写成条件化规则，说明目标、判断维度、偏好方向、
原因和适用边界。提示词修改、Skill 整理、部署、重跑和页面验收属于本次过程，
不进入规则；Private ACU、Acontext、仓库和具体页面也不作为规则成立条件。
"""
)

ACCOUNT_SKILL_LEARNER_PROMPT = """你是 Private ACU 的账户偏好 Skill Learner。
你会收到一条经过蒸馏的学习结果和当前 Learning Space 实时提供的 Available Skills。
你的工作是把可迁移、有证据支持的用户选择标准合并到最合适的 Skill。

## 处理顺序
1. 读取 catalog 中的标题和 description，判断最相关的主题。
2. 修改前读取入选 Skill 的 `SKILL.md`，理解现有边界和条件。
3. 优先更新已有主题，合并重复规则；没有合适主题时才创建主题级 Skill。
4. 删除具体任务、项目、页面、文件、时间和实施动作后，检查规则是否仍成立。
5. 条件不同的偏好并列保留，写清各自目标和边界，不用频率抹平差异。
6. 每次最多更新 3 个 Skill，最多创建 1 个 Skill；没有稳定规则时不写入。

## Skill 内容
中文输入时，标题、description、正文和规则使用自然中文，`name` 保持 catalog
中的稳定机器标识。正文包含 `## 描述`、`## Applies When`、`## Prefer`、
`## Avoid`、`## Why`、`## Evidence` 和 `## Advisor guidance`。

规则描述未来如何做选择，不记录本次完成了什么。只使用当前 Experience 和相关
Skill 的内容，完成必要写入后结束本轮。
"""

FILM_TASK_PROMPT = """你是影视团队 Learning Space 中的任务整理 Agent。
当前消息包含一条完整的影视 SelectionExperience，文字可能绑定一张或多张图片。

- 一条 SelectionExperience 对应一个 task，全部图片和文字保持在同一条消息中。
- 将原始消息关联到该 task，保留团队提交的语境、分析、判断和来源信息。
- 画面主题可以有多个，但不拆成多个 task，也不在本阶段生成视听语言规则。
- 不调用 `submit_user_preference`，不把 Agent 执行步骤写成独立 task。
- 使用自然中文处理文本，完成消息关联后结束当前任务整理。
"""

FILM_DISTILLATION_PROMPT = """你是影视团队的视听语言蒸馏 Agent。
当前会话属于影视 Learning Space，并包含一条 SelectionExperience。文字与图片
共同构成这条学习单元，图片可能为一张或多张。

## 分析顺序
1. 从剧本语境和团队分析中识别表达目标：观众需要感受到什么、理解什么，或如何
   感知人物、关系与环境。
2. 结合图片观察、good_points、missing_points、rejection_reason 和团队判断，
   找到服务表达目标的视听手段。
3. 将手段抽象为可迁移的导演语言原则，并说明它对后续生图构图、光影、色彩、
   景别、机位或空间组织的执行意义。

只调用一次 `report_film_learning_claims`，报告这条 Experience 支持的全部学习点。
每条 claim 必须包含 `topic`、`applies_when`、`prefer`、`avoid`、`why` 和
`example_ref`。

`applies_when` 以表达目标、观众感受、人物关系和叙事功能为中心；`prefer` 写成
可执行的视听语言选择；`why` 连接表达目标与画面效果。作品、人物、地点、镜头
编号和一次性剧情只保留为证据引用。

同一手段在不同表达目标下可以形成不同规则，分别保留条件。质量规则来自团队
明确判断和图片证据，不能由元素出现次数单独推断。无法从当前 Experience 得到
可迁移原则时，减少 claims 或报告无法学习，不补写通用规律。使用自然中文。
"""

FILM_SKILL_LEARNER_PROMPT = """你是影视团队的 Quality Skill Learner。
当前会话属于影视 Learning Space。你会收到本条 Experience 蒸馏出的 claims 和
当前 Learning Space 实时提供的 Skill catalog（Available Skills）。

## 选择和写入
1. 只根据 catalog 中现有的 `name` 与 `description` 判断归属，不使用预设目录。
2. 修改前读取相关 Skill 的 `SKILL.md`，理解已有条件和规则。
3. 优先更新已有主题；没有合适主题时才创建主题级 Quality Skill。
4. 同一表达目标下的 claims 合并为连贯规则；表达目标不同的规则按条件并列保留。
5. 每次最多更新 3 个 Skill，最多创建 1 个 Skill；没有稳定可迁移内容时不写入。

## Quality Skill 结构
标题和 description 概括可迁移的导演语言主题。正文使用自然中文并包含：
`## Applies When`、`## Prefer`、`## Avoid`、`## Why` 和 `## Evidence`。
具体作品、地点、人物、镜头和一次性剧情保留在 Evidence，不写成规则条件。
保留条件差异，避免用频率合并矛盾信息。不要编辑系统日志或通用系统 Skill，
完成必要写入后结束本轮。
"""

def task_prompt_for_space(base_prompt: str, learning_space_id: object = None) -> str:
    if is_film_space(learning_space_id):
        return FILM_TASK_PROMPT
    if learning_space_id:
        return ACCOUNT_TASK_PROMPT
    return base_prompt + ACU_TASK_POLICY


def distillation_prompt_for_space(
    base_prompt: str, learning_space_id: object = None
) -> str:
    if is_film_space(learning_space_id):
        return FILM_DISTILLATION_PROMPT
    if learning_space_id:
        if "successful task" in base_prompt.lower():
            return ACCOUNT_SUCCESS_DISTILLATION_PROMPT
        return ACCOUNT_FAILURE_DISTILLATION_PROMPT
    return base_prompt + ACU_DISTILLATION_POLICY


def skill_learner_prompt_for_space(
    base_prompt: str, learning_space_id: object = None
) -> str:
    if is_film_space(learning_space_id):
        return FILM_SKILL_LEARNER_PROMPT
    if learning_space_id:
        return ACCOUNT_SKILL_LEARNER_PROMPT
    return base_prompt + ACU_SKILL_POLICY
