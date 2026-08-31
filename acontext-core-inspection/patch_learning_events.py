from pathlib import Path


CONTROLLER_PATH = Path("/app/acontext_core/service/controller/skill_learner.py")
SERVICE_PATH = Path("/app/acontext_core/service/skill_learner.py")


def replace_once(path: Path, old: str, new: str) -> None:
    source = path.read_text(encoding="utf-8")
    if old not in source:
        raise RuntimeError(f"Acontext source marker is unavailable in {path}: {old[:100]!r}")
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


replace_once(
    CONTROLLER_PATH,
    "from ..data import learning_space as LS\n",
    "from ..data import learning_space as LS\n"
    "from ..learning_events import report_learning_event\n",
)
replace_once(
    CONTROLLER_PATH,
    "    wide[\"distill_outcome\"] = \"success\"\n\n"
    "    return Result.resolve(\n",
    "    wide[\"distill_outcome\"] = \"success\"\n"
    "    element_count = max(\n"
    "        1,\n"
    "        outcome.distilled_text.count(\"### Claim \"),\n"
    "        outcome.distilled_text.count(\"### Preference Element \"),\n"
    "    )\n"
    "    await report_learning_event(\n"
    "        \"distillation_completed\",\n"
    "        session_id,\n"
    "        learning_space_id,\n"
    "        task_id=task_id,\n"
    "        payload={\n"
    "            \"distilled_context\": outcome.distilled_text,\n"
    "            \"element_count\": element_count,\n"
    "        },\n"
    "    )\n\n"
    "    return Result.resolve(\n",
)

replace_once(
    SERVICE_PATH,
    "from .data import session as SD\n",
    "from .data import session as SD\n"
    "from .learning_events import report_learning_event\n",
)
replace_once(
    SERVICE_PATH,
    "    if eil:\n"
    "        wide[\"distillation_outcome\"] = \"failed\"\n"
    "        async with DB_CLIENT.get_session_context() as db_session:\n"
    "            await LS.update_session_status(db_session, body.session_id, SessionStatus.FAILED)\n"
    "        return\n",
    "    if eil:\n"
    "        wide[\"distillation_outcome\"] = \"failed\"\n"
    "        await report_learning_event(\n"
    "            \"learning_failed\",\n"
    "            body.session_id,\n"
    "            learning_space_id,\n"
    "            task_id=body.task_id,\n"
    "            payload={\"stage\": \"distillation\", \"error\": str(eil)},\n"
    "        )\n"
    "        async with DB_CLIENT.get_session_context() as db_session:\n"
    "            await LS.update_session_status(db_session, body.session_id, SessionStatus.FAILED)\n"
    "        return\n",
)
replace_once(
    SERVICE_PATH,
    "    if distilled_payload is None:\n"
    "        wide[\"distillation_outcome\"] = \"skipped_not_worth\"\n"
    "        async with DB_CLIENT.get_session_context() as db_session:\n"
    "            await LS.update_session_status(db_session, body.session_id, SessionStatus.COMPLETED)\n"
    "        return\n",
    "    if distilled_payload is None:\n"
    "        wide[\"distillation_outcome\"] = \"skipped_not_worth\"\n"
    "        await report_learning_event(\n"
    "            \"learning_skipped\",\n"
    "            body.session_id,\n"
    "            learning_space_id,\n"
    "            task_id=body.task_id,\n"
    "            payload={\"stage\": \"distillation\", \"reason\": \"not_worth_learning\"},\n"
    "        )\n"
    "        async with DB_CLIENT.get_session_context() as db_session:\n"
    "            await LS.update_session_status(db_session, body.session_id, SessionStatus.COMPLETED)\n"
    "        return\n",
)
replace_once(
    SERVICE_PATH,
    "    try:\n"
    "        r = await SLC.run_skill_agent(\n",
    "    try:\n"
    "        await report_learning_event(\n"
    "            \"skill_write_started\",\n"
    "            body.session_id,\n"
    "            body.learning_space_id,\n"
    "            task_id=body.task_id,\n"
    "        )\n"
    "        r = await SLC.run_skill_agent(\n",
)
replace_once(
    SERVICE_PATH,
    "        if eil:\n"
    "            wide[\"agent_outcome\"] = \"failed\"\n"
    "            async with DB_CLIENT.get_session_context() as db_session:\n"
    "                await LS.update_session_status(db_session, body.session_id, SessionStatus.FAILED)\n"
    "        else:\n",
    "        if eil:\n"
    "            wide[\"agent_outcome\"] = \"failed\"\n"
    "            await report_learning_event(\n"
    "                \"learning_failed\",\n"
    "                body.session_id,\n"
    "                body.learning_space_id,\n"
    "                task_id=body.task_id,\n"
    "                payload={\"stage\": \"skill_write\", \"error\": str(eil)},\n"
    "            )\n"
    "            async with DB_CLIENT.get_session_context() as db_session:\n"
    "                await LS.update_session_status(db_session, body.session_id, SessionStatus.FAILED)\n"
    "        else:\n",
)
replace_once(
    SERVICE_PATH,
    "            wide[\"sessions_completed\"] = [str(s) for s in all_session_ids]\n"
    "            async with DB_CLIENT.get_session_context() as db_session:\n",
    "            wide[\"sessions_completed\"] = [str(s) for s in all_session_ids]\n"
    "            await report_learning_event(\n"
    "                \"skill_write_completed\",\n"
    "                body.session_id,\n"
    "                body.learning_space_id,\n"
    "                task_id=body.task_id,\n"
    "                payload={\"session_ids\": [str(s) for s in all_session_ids]},\n"
    "            )\n"
    "            async with DB_CLIENT.get_session_context() as db_session:\n",
)
replace_once(
    SERVICE_PATH,
    "    except Exception as e:\n"
    "        wide[\"agent_outcome\"] = \"error\"\n"
    "        wide[\"error\"] = {\"type\": type(e).__name__, \"message\": str(e)}\n"
    "        async with DB_CLIENT.get_session_context() as db_session:\n",
    "    except Exception as e:\n"
    "        wide[\"agent_outcome\"] = \"error\"\n"
    "        wide[\"error\"] = {\"type\": type(e).__name__, \"message\": str(e)}\n"
    "        await report_learning_event(\n"
    "            \"learning_failed\",\n"
    "            body.session_id,\n"
    "            body.learning_space_id,\n"
    "            task_id=body.task_id,\n"
    "            payload={\"stage\": \"skill_write\", \"error\": str(e)},\n"
    "        )\n"
    "        async with DB_CLIENT.get_session_context() as db_session:\n",
)
