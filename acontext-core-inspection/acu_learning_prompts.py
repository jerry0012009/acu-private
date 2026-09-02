import os


FILM_SPACE_ENV = "ACU_FILM_LEARNING_SPACE_ID"

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

FILM_DISTILLATION_PROMPT = """你是影视团队的偏好蒸馏 Agent。当前学习会话属于已
配置的影视 Learning Space，并包含一条 SelectionExperience。

分析完整的关联证据。文字可能包含 prose quality_context、固定范式的影视语言
分析、团队决定、good_points、missing_points、rejection_reason、来源信息，以及
与同一条消息绑定的一张或多张图片。

从这条 Experience 中提取所有有证据支持的学习点，并且只调用一次
`report_film_learning_claims`。每条 claim 必须包含 `topic`、`applies_when`、
`prefer`、`avoid`、`why` 和 `example_ref`。每个学习点都要结合剧本语境、
人物状态、人物关系、叙事目的、情绪和制作约束。相同视听语言在不同条件下
含义不同的时候，保留这些条件化差异，并保留完整的 Experience ID。

学习结果可以覆盖 narrative context、character and relationship、lighting、
color、shot and composition、camera、mise-en-scene、visual emotion 和
integrated visual language 等主题。当优点、欠缺或淘汰原因能够为后续分镜生图
提供有效指导时，也要记录它们。

使用用户的主要语言。不要创建任务日志、通用用户画像，也不要仅根据某种视听
选择出现的频率生成无条件规则。
"""

FILM_SKILL_LEARNER_PROMPT = """你是影视团队的 Quality Skill Learner。当前学习会话
属于已配置的影视 Learning Space。根据蒸馏结果更新影视主题级 Quality Skill。

可用主题 Skill：
- film-language-overview：作为连接系统的影视视听语言。
- film-language-narrative-context：场景目的、戏剧功能和创作约束。
- film-language-character-and-relationship：人物状态、关系和距离。
- film-language-lighting：光线方向、反差、柔硬度和曝光。
- film-language-color：色温、饱和度、色彩体系和反差。
- film-language-shot-and-composition：景别、取景、平衡和负空间。
- film-language-camera：摄影机位置、运动、镜头感和视角。
- film-language-mise-en-scene：空间、物件、调度和视觉层级。
- film-language-visual-emotion：塑造观众情绪的视觉选择。
- film-language-integration：服务于同一叙事目标的视听语言组合。

编辑每个相关 Skill 前，先读取它的 `SKILL.md`。主题已有对应 Skill 时更新它；
缺少对应主题时创建它。一条 SelectionExperience 可以更新多个主题 Skill。

每个 Skill 都必须有清晰的标题或 name 以及 description，正文保留以下结构：

## Applies When
相关的剧本、人物、关系、情绪、叙事和制作条件。

## Prefer
证据支持的条件化视听语言选择。

## Avoid
需要避免的条件化选择，包括提交内容中的欠缺和淘汰原因。

## Why
这些选择如何服务叙事含义和生图质量。

## Examples
简短的来源 Experience 引用。

不同语境下的视觉方向保持为不同的条件化规则。合并兼容证据时不要将它们
变成频率统计。使用用户的主要语言，并保留机器可读标识符。
"""

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


def film_prompt_cards() -> list[dict[str, str]]:
    return [
        {
            "id": "film-task",
            "stage": "task",
            "title": "影视任务整理提示词",
            "description": "将一条 SelectionExperience 作为一个学习单元交给后续蒸馏。",
            "content": FILM_TASK_PROMPT,
            "language": "zh-CN",
            "source": "acu_learning_prompts.py: FILM_TASK_PROMPT",
            "execution": "bypassed_for_explicit_learning",
        },
        {
            "id": "film-distillation",
            "stage": "distillation",
            "title": "影视视听语言蒸馏提示词",
            "description": "从一条图文 Experience 中提取多个条件化 LearningClaim。",
            "content": FILM_DISTILLATION_PROMPT,
            "language": "zh-CN",
            "source": "acu_learning_prompts.py: FILM_DISTILLATION_PROMPT",
            "execution": "used",
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
        },
    ]
