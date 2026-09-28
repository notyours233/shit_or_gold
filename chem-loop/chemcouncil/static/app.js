const STORAGE = {
  lang: "chemcouncil_lang",
  theme: "chemcouncil_theme",
  manual_draft_prefix: "chemcouncil_material_feedback_draft_v2_",
  manual_open_recos: "chemcouncil_material_feedback_open_recos_v2",
  manual_active_reco: "chemcouncil_material_feedback_active_reco_v2",
  analysis_agg_kind: "chemcouncil_analysis_agg_kind_v1",
  analysis_agg_step: "chemcouncil_analysis_agg_step_v1",
  experience_page: "chemcouncil_experience_page_v1",
  experience_page_size: "chemcouncil_experience_page_size_v1",
};

const I18N = {
  zh: {
    app_subtitle: "材料名称中心的 19 方向性能经验库与推荐",
    tz_hint: "时间显示：北京时间 (UTC+8)",
    lang_label: "语言",
    theme_toggle_dark: "主题：深色",
    theme_toggle_light: "主题：浅色",
    nav_recommend: "性能推荐",
    nav_history: "历史推荐",
    nav_feedback: "经验反馈",
    nav_experience_build: "生成经验库",
    nav_experience: "经验库",
    nav_analysis: "效果评估",

    recommend_title: "材料性能推荐",
    recommend_desc:
      "材料名称为必填项。你可以补充结构化材料信息或自定义描述，选择一个性能方向进行多智能体辩论，或分别运行全部 19 个方向后统一排序。",
    recommend_material_count_label: "推荐材料条数",
    recommend_material_count_hint: "一次最多提交 10 条材料；每条材料会生成独立推荐任务，结果在下方汇总。",
    recommend_material_card_title: "材料条目",
    recommend_material_card_hint: "材料名称必填；提示词和结构化信息按条目分别填写。",
    recommend_batch_submitting: "正在提交材料推荐任务",
    recommend_batch_progress: "已完成 {done}/{total} 条",
    recommend_batch_result_title: "批量推荐结果",
    recommend_batch_failed_item: "提交失败",
    recommend_batch_empty: "没有成功提交任何材料推荐任务。",
    material_serial_no_label: "材料序号（正整数）",
    material_serial_no_hint: "用于跨批次查找；默认按当前填写顺序生成，可修改为任意正整数。",
    material_name_label: "材料名称（必填）",
    material_name_placeholder: "例如：CuO、MoS2负载CuO纳米颗粒、ZnO包覆的CoO",
    material_name_hint: "材料名称是唯一必填字段；缺失的制备、元素和条件信息会直接省略。",
    custom_prompt_label: "自定义材料描述（可选）",
    custom_prompt_placeholder: "可直接填写实验人员整理的一段材料提示词",
    custom_prompt_hint: "该文本只作为材料数据，不会覆盖系统提示词、辩论协议或输出格式。",
    structured_material_fields: "结构化材料信息（可选）",
    major_category_label: "材料大类",
    material_components_label: "材料组分",
    structure_relationships_label: "结构关系",
    precursors_label: "前驱体（用逗号分隔）",
    feed_ratio_label: "投料比",
    preparation_method_label: "制备方式",
    elements_label: "元素（金属和非金属，用逗号分隔）",
    element_content_label: "元素含量",
    conditions_label: "实验或测试条件",
    recommend_task_type_label: "性能方向",
    recommend_task_type_hint: "单方向只运行一组多智能体辩论；选择全部时，外层分别运行 19 组独立辩论再排序。",
    components_label: "材料组分",
    components_placeholder: "例如：MoS2、CuO 纳米颗粒",
    components_hint: "可填写材料组分；元素、比例和结构信息也可以分别填写。",
    recommend_other_metals_label: "其它元素或杂质（可选）",
    recommend_other_metals_hint: "可记录未包含在主要材料描述中的痕量元素或杂质。",
    property_types_default_label: "系统默认比较的任务方向",
    property_types_default_hint:
      "共支持 19 个方向：9 个电化学反应方向 + 10 个材料与新增性能方向。每组辩论只预测一个方向。",
    reaction_types_default_label: "系统默认比较的任务方向",
    reaction_types_default_hint:
      "默认共比较 19 个方向：9 个电化学反应方向 + 10 个材料与新增性能方向；每个方向单独辩论。",
    advanced_settings: "高级设置（可选）",
    recommend_topk_label: "Top-K 推荐方向数",
    recommend_topk_hint: "全部方向或方向子集完成后，按任务特异标准化评分返回前 K 个；单方向时有效值自动为 1。",
    recommend_parallel_label: "同时评估方向数",
    recommend_parallel_hint:
      "默认 1 最稳妥。如果你在服务器上内存充足，可尝试 2–3；太大可能会 OOM。",
    recommend_save_each_label: "保存每个方向的详细辩论记录（用于后续蒸馏经验）",
    btn_start_recommend: "开始推荐",
    btn_view_log: "查看日志",
    btn_stop_job: "停止任务",
    status_idle: "尚未开始。",
    log_section: "运行日志（可选）",

    experience_build_title: "统一经验库生成",
    experience_build_desc:
      "先确定性重建并上传已审计的 19 方向性能数据，再用 Training-Free GRPO 蒸馏 MaterialCard 经验库并同步到 MAD。推荐时按当前单一性能方向检索经验。",
    experience_build_flow_label: "当前主流程",
    experience_build_step_dataset: "1 性能数据库 → GRPO数据集",
    experience_build_step_grpo: "2 GRPO生成经验库",
    experience_build_step_sync: "3 同步 experience.yaml",
    experience_build_step_recommend: "4 再执行推荐",
    experience_build_mode_label: "运行方式",
    experience_build_mode_prepare: "只准备/上传数据集",
    experience_build_mode_pilot: "小批量经验库试跑",
    experience_build_mode_full: "全量 11,291 条经验库生成",
    experience_build_mode_hint:
      "只准备数据集不调用模型；小批量适合先验证 RAG、模型和经验卡合同；全量模式会处理全部 11,291 条点值样本，调用成本较高。",
    experience_build_exp_name_label: "实验名（可选）",
    experience_build_exp_name_hint: "留空时后端会自动生成唯一名称，避免覆盖已有结果。",
    experience_build_truncate_label: "样本数上限（TRUNCATE）",
    experience_build_truncate_hint: "pilot 建议 30–60；完整构建为 11,291 条点值样本。",
    experience_build_batch_label: "batch_size",
    experience_build_batch_hint: "pilot 建议 10；完整构建默认 50。",
    experience_build_grpo_n_label: "grpo_n",
    experience_build_grpo_n_hint: "pilot 建议 2；完整构建默认 3。",
    experience_build_concurrency_label: "rollout_concurrency",
    experience_build_concurrency_hint: "RAG 会加载 Chroma，建议从 1 开始。",
    experience_build_rag_label: "启用文献 RAG",
    experience_build_resume_label: "续跑已有同名实验",
    btn_start_experience_build: "开始生成经验库",
    prepared_prefix: "已准备",

    feedback_title: "材料性能真值反馈",
    feedback_desc:
      "材料名称是唯一必填的材料字段。可直接填写材料与真实性能，也可关联一次历史推荐，自动带入材料提示词和预测值用于误差对齐。提交后，系统使用单智能体 Training-Free GRPO 增量更新经验库。",
    tab_upload: "上传文件",
    tab_manual: "手动填写",
    upload_file_label: "上传实验记录（CSV 或 XLSX）",
    upload_file_hint:
      "新版列：material_name / task_type / value / unit；可选 material_serial_no、material_input_json、custom_prompt、elements、condition、notes 和 recommendation_job_id。系统会统一单位后生成训练样本；少量数据可作为不满批次运行，与测试配置对齐时建议积累到 19 条。",
    btn_download_template: "下载 CSV 模板",
    manual_hint:
      "每个反馈块对应一种材料，可填写该材料在一个或多个性能方向上的真实值。历史推荐仅用于自动带入材料信息、显示预测参考和关联辩论轨迹，不是提交反馈的前提。",
    reco_search_label: "查找历史推荐以关联（可选）",
    reco_search_hint: "输入材料名称或性能方向（例如 CuO、conductivity）后选择历史推荐；也可以直接在下方填写新材料。",
    btn_add_reco_group: "添加材料反馈块",
    reco_groups_hint: "可一次提交多个材料块。不勾选时只提交当前编辑块；勾选后提交所有已勾选且材料名称和真值完整的块。",
    manual_group_submit_label: "加入本次提交",
    manual_group_reco_label: "关联历史推荐（可选）",
    manual_group_scope_label: "元素信息范围（兼容字段）",
    manual_group_scope_hint: "可在右侧补充材料描述中未列出的其它元素或杂质。",
    manual_group_other_metals_label: "其它元素/杂质（可选）",
    btn_remove_group: "移除该块",
    reco_select_label: "选择要反馈的推荐记录",
    reco_select_hint: "请选择与你本次实验对应的那条历史推荐（通常选最新的一条）。",
    col_reaction: "性能方向",
    col_predicted: "系统预测（参考）",
    col_value: "真实性能数据",
    col_unit: "单位",
    col_condition: "条件",
    col_product: "备注",
    feedback_prompt_preview: "组装后的材料提示词预览",
    btn_add_row: "添加一行",
    btn_clear_draft: "清空当前草稿",
    tag_label: "标签（用于命名数据集）",
    tag_hint: "例如：sample_A / 20260307 / batch3。用于追踪这次反馈来自哪一批实验。",
    update_advanced_hint:
      "默认值来自当前 19 方向 held-out 超参数测试：epochs=1、batch_size=19、grpo_n=3、rollout_concurrency=4、RAG=1。少于 19 条时仍会作为一个不满批次运行。",
    batch_size_label: "每轮处理多少条记录（batch_size）",
    batch_size_hint: "测试选定值为 19，后端固定使用该值；少量反馈不会因不足 19 条而失败。",
    grpo_n_label: "每条记录生成多少个候选回答（grpo_n）",
    grpo_n_hint: "测试选定值为 3；越大越慢且更费额度。",
    rollout_c_label: "并行调用模型数量（rollout_concurrency）",
    rollout_c_hint:
      "测试固定值为 4；如果服务商限流或本机资源不足，可临时调低。",
    epochs_label: "重复轮数（epochs）",
    epochs_hint: "测试选定值为 1；增加轮数会显著增加调用量。",
    feedback_rag_label: "文献检索（RAG）",
    feedback_rag_hint: "当前测试配置固定启用 RAG。",
    btn_start_update: "开始更新经验库",

    history_title: "历史推荐（查看/复用/隐藏）",
    history_desc:
      "这里集中展示你跑过的推荐任务（MAD rank）。你可以查看结果/日志，也可以一键跳转到“经验反馈”并选择对应的推荐记录来填写实验数据。提示：这里的“隐藏”是软删除（可恢复），不会删除结果文件/日志文件。",
    history_search_label: "筛选（序号/材料名称/描述/方向）",
    history_search_hint: "输入材料序号（例如 17）、CuO、MoS2、OER 等关键字后按回车或点刷新。",
    history_show_deleted_label: "显示已隐藏",
    history_raw_jobs_title: "原始 Jobs（JSON）",
    btn_use_for_feedback: "用于反馈",
    btn_hide_job: "隐藏（可恢复）",
    btn_restore_job: "恢复",
    btn_view_result: "查看结果",

    experience_title: "经验库（当前 + 历史）",
    experience_desc: "你可以查看当前生效的经验库，也可以浏览历史版本、下载或一键切换（用于回滚到未污染版本）。",
    btn_refresh: "刷新",
    btn_clear: "清空",
    btn_hide_round: "删除此回合",
    btn_ignore_row: "忽略此条",
    btn_unignore_row: "恢复",
    btn_go_experience_rollback: "回滚经验库",
    btn_go_feedback_resubmit: "重新提交反馈",
    analysis_ignore_tip:
      "提示：忽略只影响效果评估统计，不会回滚经验库。若经验库已被错误数据污染，请到「经验库」回滚到未污染版本，然后重新提交反馈。",
    btn_download_current: "下载当前 experience.yaml",
    experience_view_current: "查看当前经验库内容",
    experience_view_hint: "下方会解析出 [G0]...[Gx] 经验条目；也可展开查看原始 YAML。",
    experience_search_label: "检索经验（可选）",
    experience_search_placeholder: "例如：conductivity / Fe / thermal",
    experience_search_hint: "支持多关键词（空格/逗号分隔），会检索 MaterialCard、旧 CaseCard 和段落正文。",
    experience_view_raw: "查看原始 YAML",
    experience_history_title: "历史经验库（归档）",

    analysis_title: "效果评估（预测 vs 实验）",
    analysis_desc:
      "把系统预测值和你反馈的真实实验值做对比。主要看统一单位后的相对误差（越低越好）。你可以切换“按记录分组（每 N 条一个点）”或“按回合（每次反馈一个点）”。",
    analysis_agg_kind_label: "展示方式",
    analysis_agg_step_label: "每点条数",
    analysis_agg_kind_records_bucket: "按记录分桶（每 N 条=1 点）",
    analysis_agg_kind_records_cumulative: "按记录累积（1–N, 1–2N, …）",
    analysis_agg_kind_rounds: "按回合（每次反馈=1 点）",
    analysis_records_title: "原始记录（JSON）",

    // dynamic
    queued_prefix: "排队中",
    running_prefix: "运行中",
    completed_prefix: "已完成",
    failed_prefix: "失败",
    cancelling_prefix: "停止中",
    cancelled_prefix: "已停止",
    job_id: "任务ID",
    started_at: "开始",
    finished_at: "结束",
    elapsed: "已用时",
    duration: "总耗时",
    beijing: "北京时间",
    download_json: "下载结果 JSON",
    evidence_rag: "证据：文献检索 (RAG)",
    evidence_llm: "证据：模型推断 (LLM)",
    consensus_yes: "共识：是",
    consensus_no: "共识：否",
    elements_detected: "检索用元素（自动提取）",
    elements_need_5: "材料名称为必填项",
    loading: "加载中…",
    empty: "（空）",
    view: "查看",
    download: "下载",
    activate: "启用",
    submitting: "正在提交…",
    uploading_starting: "正在上传并开始运行…",
    no_guidelines: "未检测到 [Gx] 经验条目",
    manual_no_rows: "请填写材料名称，并至少填写一行完整的真实性能数据。",
  },
  en: {
    app_subtitle: "Material-name-centered experience and recommendation across 19 directions",
    tz_hint: "Time display: China Standard Time (UTC+8)",
    lang_label: "Language",
    theme_toggle_dark: "Theme: Dark",
    theme_toggle_light: "Theme: Light",
    nav_recommend: "Recommendations",
    nav_history: "History",
    nav_feedback: "Feedback",
    nav_experience_build: "Build Experience",
    nav_experience: "Experience Library",
    nav_analysis: "Analytics",

    recommend_title: "Material performance recommendation",
    recommend_desc:
      "Material name is required. Add structured fields or a free-form material description, then run one task debate or 19 independent debates followed by ranking.",
    recommend_material_count_label: "Number of materials",
    recommend_material_count_hint: "Submit up to 10 materials at once. Each material creates an independent recommendation job and results are grouped below.",
    recommend_material_card_title: "Material entry",
    recommend_material_card_hint: "Material name is required; prompts and structured fields belong to this entry only.",
    recommend_batch_submitting: "Submitting material recommendation jobs",
    recommend_batch_progress: "Completed {done}/{total}",
    recommend_batch_result_title: "Batch recommendation results",
    recommend_batch_failed_item: "Submission failed",
    recommend_batch_empty: "No material recommendation job was submitted successfully.",
    material_serial_no_label: "Material serial number (positive integer)",
    material_serial_no_hint: "Use this number to find an entry across batches. It is filled from the current order by default and can be changed.",
    material_name_label: "Material name (required)",
    material_name_placeholder: "e.g. CuO, CuO nanoparticles on MoS2, ZnO-coated CoO",
    material_name_hint: "This is the only required field; missing synthesis, composition, and condition fields are omitted.",
    custom_prompt_label: "Custom material description (optional)",
    custom_prompt_placeholder: "Enter an experimenter-authored material prompt",
    custom_prompt_hint: "This is material data and cannot override system instructions or the debate/output contract.",
    structured_material_fields: "Structured material fields (optional)",
    major_category_label: "Major category",
    material_components_label: "Components",
    structure_relationships_label: "Structure relationships",
    precursors_label: "Precursors (comma-separated)",
    feed_ratio_label: "Feed ratio",
    preparation_method_label: "Preparation method",
    elements_label: "Elements, including metals and nonmetals",
    element_content_label: "Element content",
    conditions_label: "Experimental or test conditions",
    recommend_task_type_label: "Performance direction",
    recommend_task_type_hint: "One direction runs one multi-agent debate; All runs 19 independent debates before ranking.",
    components_label: "Material components",
    components_placeholder: "Example: MoS2, CuO nanoparticles",
    components_hint: "Components are optional; elements, ratios, and structural relationships can be entered separately.",
    recommend_other_metals_label: "Other elements/impurities (optional)",
    recommend_other_metals_hint: "Record trace elements or impurities omitted from the primary material description.",
    property_types_default_label: "Task directions compared by default",
    property_types_default_hint:
      "The system supports 19 directions: 9 electrochemical and 10 material/new-performance tasks. Each debate predicts one direction.",
    reaction_types_default_label: "Task directions compared by default",
    reaction_types_default_hint:
      "All 19 directions are available: 9 electrochemical and 10 material/new-performance directions. Each runs an independent debate.",
    advanced_settings: "Advanced (optional)",
    recommend_topk_label: "Top-K recommendation directions",
    recommend_topk_hint: "After all selected directions finish, return the top K by task-specific normalized score. A single direction is automatically capped at 1.",
    recommend_parallel_label: "Directions evaluated concurrently",
    recommend_parallel_hint:
      "This controls independent direction debates, not the four models inside one debate. Default 1 is safest; larger values use more memory and provider capacity.",
    recommend_save_each_label: "Save detailed debate traces (for later distillation)",
    btn_start_recommend: "Start ranking",
    btn_view_log: "View log",
    btn_stop_job: "Stop job",
    status_idle: "Idle.",
    log_section: "Run log (optional)",

    experience_build_title: "Build unified experience library",
    experience_build_desc:
      "Deterministically rebuild and upload the audited 19-direction dataset, run Training-Free GRPO to distill MaterialCards, and sync the stable experience.yaml into MAD. Retrieval is scoped to the current single task.",
    experience_build_flow_label: "Main workflow",
    experience_build_step_dataset: "1 Performance DB → GRPO dataset",
    experience_build_step_grpo: "2 GRPO builds experience",
    experience_build_step_sync: "3 Sync experience.yaml",
    experience_build_step_recommend: "4 Then recommend",
    experience_build_mode_label: "Run mode",
    experience_build_mode_prepare: "Prepare/upload dataset only",
    experience_build_mode_pilot: "Small GRPO pilot",
    experience_build_mode_full: "Full 11,291-sample build",
    experience_build_mode_hint:
      "Prepare-only makes no model calls. Pilot verifies RAG, model, and card contracts. Full mode processes all 11,291 point-value samples and has substantial model cost.",
    experience_build_exp_name_label: "Experiment name (optional)",
    experience_build_exp_name_hint: "Leave blank and the backend will create a unique name.",
    experience_build_truncate_label: "Sample cap (TRUNCATE)",
    experience_build_truncate_hint: "Use 30-60 for pilots; the full point-value dataset has 11,291 samples.",
    experience_build_batch_label: "batch_size",
    experience_build_batch_hint: "Pilot suggestion: 10; full-build default: 50.",
    experience_build_grpo_n_label: "grpo_n",
    experience_build_grpo_n_hint: "Pilot suggestion: 2; full-build default: 3.",
    experience_build_concurrency_label: "rollout_concurrency",
    experience_build_concurrency_hint: "RAG loads Chroma; start from 1.",
    experience_build_rag_label: "Enable literature RAG",
    experience_build_resume_label: "Resume same experiment",
    btn_start_experience_build: "Build experience",
    prepared_prefix: "Prepared",

    feedback_title: "Material performance ground-truth feedback",
    feedback_desc:
      "Material name is the only required material field. Enter a material and its measured performance directly, or optionally link a previous recommendation to reuse its prompt and align predictions with ground truth. Submission runs a single-agent Training-Free GRPO incremental update.",
    tab_upload: "Upload file",
    tab_manual: "Manual entry",
    upload_file_label: "Upload lab records (CSV or XLSX)",
    upload_file_hint:
      "Current columns: material_name / task_type / value / unit, with optional material_serial_no, material_input_json, custom_prompt, elements, condition, notes, and recommendation_job_id. Small uploads run as a partial batch; accumulate 19 samples when practical to match the tested configuration.",
    btn_download_template: "Download CSV template",
    manual_hint:
      "Each block represents one material and can contain ground truth for one or more performance directions. Linking history only imports material fields, shows prediction references, and connects debate traces; it is not required.",
    reco_search_label: "Find a recommendation to link (optional)",
    reco_search_hint: "Search by material or task (for example CuO or conductivity), or enter a new material directly below.",
    btn_add_reco_group: "Add material feedback block",
    reco_groups_hint: "Submit multiple materials by ticking their blocks. With none ticked, only the active block is submitted.",
    manual_group_submit_label: "Include in submit",
    manual_group_reco_label: "Linked recommendation (optional)",
    manual_group_scope_label: "Element scope (compatibility field)",
    manual_group_scope_hint: "Use the field on the right for additional elements or impurities absent from the material description.",
    manual_group_other_metals_label: "Other elements/impurities (optional)",
    btn_remove_group: "Remove block",
    reco_select_label: "Select recommendation to feed back",
    reco_select_hint: "Pick the recommendation that matches your current experiment (usually the newest one).",
    col_reaction: "Performance direction",
    col_predicted: "Predicted (reference)",
    col_value: "Measured performance",
    col_unit: "Unit",
    col_condition: "Condition",
    col_product: "Notes",
    feedback_prompt_preview: "Assembled material prompt preview",
    btn_add_row: "Add row",
    btn_clear_draft: "Clear draft",
    tag_label: "Tag (used in dataset naming)",
    tag_hint: "Example: sample_A / 20260307 / batch3. Helps trace which lab batch it came from.",
    update_advanced_hint:
      "Defaults come from the current 19-direction held-out sweep: epochs=1, batch_size=19, grpo_n=3, rollout_concurrency=4, and RAG=1. Fewer than 19 samples still run as one partial batch.",
    batch_size_label: "Records per update step (batch_size)",
    batch_size_hint: "The tested value is 19 and is fixed by the backend; smaller uploads do not fail.",
    grpo_n_label: "Candidates per record (grpo_n)",
    grpo_n_hint: "The tested value is 3; larger values are slower and consume more quota.",
    rollout_c_label: "Parallel model calls (rollout_concurrency)",
    rollout_c_hint: "The sweep fixed this at 4; lower it temporarily if the provider rate-limits or local resources are constrained.",
    epochs_label: "Epochs",
    epochs_hint: "The tested value is 1; extra epochs substantially increase model calls.",
    feedback_rag_label: "Literature retrieval (RAG)",
    feedback_rag_hint: "RAG is enabled in the tested configuration.",
    btn_start_update: "Start update",

    history_title: "Recommendation history",
    history_desc:
      "Browse previous MAD rank runs. You can view result/logs, or jump to Manual feedback and attach lab data to a specific recommendation record. Note: “Hide” is a reversible soft-delete and does not remove the result/log files.",
    history_search_label: "Filter (serial/material/description/task)",
    history_search_hint: "Type a material serial number (for example 17), CuO, MoS2, OER, or another keyword and press Enter or Refresh.",
    history_show_deleted_label: "Show hidden",
    history_raw_jobs_title: "Raw jobs (JSON)",
    btn_use_for_feedback: "Use for feedback",
    btn_hide_job: "Hide (reversible)",
    btn_restore_job: "Restore",
    btn_view_result: "View result",

    experience_title: "Experience library (current + history)",
    experience_desc: "Browse the active experience pack and archived versions. You can also activate an older pack (rollback) if needed.",
    btn_refresh: "Refresh",
    btn_clear: "Clear",
    btn_hide_round: "Delete round",
    btn_ignore_row: "Ignore row",
    btn_unignore_row: "Restore",
    btn_go_experience_rollback: "Rollback experience pack",
    btn_go_feedback_resubmit: "Resubmit feedback",
    analysis_ignore_tip:
      "Note: ignoring only affects Analytics statistics; it does not roll back the experience pack. If the pack was contaminated by wrong data, roll back to a previous version and resubmit feedback.",
    btn_download_current: "Download current experience.yaml",
    experience_view_current: "View current experience contents",
    experience_view_hint: "We extract [G0]...[Gx] guideline items; you can also view raw YAML.",
    experience_search_label: "Search guidelines (optional)",
    experience_search_placeholder: "e.g., conductivity / Fe / thermal",
    experience_search_hint: "Space/comma separated keywords; searches MaterialCards, legacy CaseCards, and prose guidelines.",
    experience_view_raw: "View raw YAML",
    experience_history_title: "Archived experience packs",

    analysis_title: "Analytics (prediction vs experiment)",
    analysis_desc:
      "Compare the system’s predicted values with your real experimental values after unit normalization. We focus on relative error (lower is better). You can switch between record-based grouping (every N records as a point) and round-based grouping (each feedback update as a point).",
    analysis_agg_kind_label: "View",
    analysis_agg_step_label: "Step",
    analysis_agg_kind_records_bucket: "By records (bucket; every N records = 1 point)",
    analysis_agg_kind_records_cumulative: "By records (cumulative; 1–N, 1–2N, …)",
    analysis_agg_kind_rounds: "By rounds (each feedback update = 1 point)",
    analysis_records_title: "Raw records (JSON)",

    // dynamic
    queued_prefix: "Queued",
    running_prefix: "Running",
    completed_prefix: "Completed",
    failed_prefix: "Failed",
    cancelling_prefix: "Cancelling",
    cancelled_prefix: "Cancelled",
    job_id: "Job",
    started_at: "Start",
    finished_at: "Finish",
    elapsed: "Elapsed",
    duration: "Duration",
    beijing: "CST (UTC+8)",
    download_json: "Download result JSON",
    evidence_rag: "Evidence: literature RAG",
    evidence_llm: "Evidence: LLM only",
    consensus_yes: "Consensus: Yes",
    consensus_no: "Consensus: No",
    elements_detected: "Retrieval elements (auto-detected)",
    elements_need_5: "Material name is required",
    loading: "Loading…",
    empty: "(empty)",
    view: "View",
    download: "Download",
    activate: "Activate",
    submitting: "Submitting…",
    uploading_starting: "Uploading & starting…",
    no_guidelines: "(no [Gx] items detected)",
    manual_no_rows: "Enter a material name and at least one complete measured-performance row.",
  },
};

const MATERIAL_PROPERTY_TYPES = [
  { key: "photothermal_conversion_efficiency", zh: "光热转换效率", en: "Photothermal conversion efficiency" },
  { key: "conductivity", zh: "电导率", en: "Electrical conductivity" },
  { key: "thermal_conductivity", zh: "热导率", en: "Thermal conductivity" },
  { key: "ferromagnetism", zh: "铁磁性", en: "Ferromagnetism" },
  { key: "ferrimagnetism", zh: "亚铁磁性", en: "Ferrimagnetism" },
  { key: "antiferromagnetism", zh: "反铁磁性", en: "Antiferromagnetism" },
  { key: "photocatalytic_h2o2", zh: "光催化 H2O2", en: "Photocatalytic H2O2" },
  { key: "antibacterial", zh: "抗菌性能", en: "Antibacterial" },
  { key: "thermoelectric", zh: "热电性能", en: "Thermoelectric" },
  { key: "furfural_hydrogenation", zh: "糠醛加氢", en: "Furfural hydrogenation" },
];

const REACTION_TASK_TYPES = [
  { key: "HER", zh: "HER 析氢反应", en: "HER" },
  { key: "OER", zh: "OER 析氧反应", en: "OER" },
  { key: "ORR", zh: "ORR 氧还原反应", en: "ORR" },
  { key: "HOR", zh: "HOR 氢氧化反应", en: "HOR" },
  { key: "UOR", zh: "UOR 尿素氧化反应", en: "UOR" },
  { key: "EOR", zh: "EOR 乙醇氧化反应", en: "EOR" },
  { key: "HZOR", zh: "HZOR 肼氧化反应", en: "HZOR" },
  { key: "O5H", zh: "O5H", en: "O5H" },
  { key: "CO2RR", zh: "CO2RR 二氧化碳还原", en: "CO2RR" },
];

const REACTION_TYPES = [...REACTION_TASK_TYPES, ...MATERIAL_PROPERTY_TYPES];
const DEFAULT_PROPERTY_TYPE = "HER";

const MATERIAL_UNIT_OPTIONS = [
  { v: "%", label: "%" },
  { v: "mV", label: "mV" },
  { v: "V", label: "V" },
  { v: "mA cm-2", label: "mA cm-2" },
  { v: "A mgmetal-1", label: "A mgmetal-1" },
  { v: "S/m", label: "S/m" },
  { v: "S/cm", label: "S/cm" },
  { v: "mS/cm", label: "mS/cm" },
  { v: "mS/m", label: "mS/m" },
  { v: "W m-1 K-1", label: "W m-1 K-1" },
  { v: "W/mK", label: "W/mK" },
  { v: "emu/g", label: "emu/g" },
  { v: "A m2/kg", label: "A m2/kg" },
  { v: "K", label: "K" },
  { v: "ppm", label: "ppm" },
  { v: "ug/mL", label: "ug/mL" },
  { v: "mg/L", label: "mg/L" },
  { v: "dimensionless", label: "dimensionless" },
];

// Selected by the 19-direction held-out sweep; the runner supports a final partial batch.
const FIXED_UPDATE_BATCH_SIZE = 19;
const EXPERIENCE_PROSE_PREVIEW_MAX_CHARS = 90;
const MANUAL_DRAFT_SCHEMA_VERSION = 2;
const MAX_RECOMMEND_MATERIALS = 10;
const RECOMMEND_MATERIAL_TEXT_FIELDS = [
  "major_category",
  "components",
  "structure_relationships",
  "feed_ratio",
  "preparation_method",
  "element_content",
  "conditions",
  "custom_prompt",
];

let recommendMaterialDrafts = [{}];
let recommendMaterialCount = 1;

function isInteractiveDomTarget(el) {
  const node = el && el.nodeType === 1 ? el : null;
  if (!node) return false;
  const tag = String(node.tagName || "").toLowerCase();
  if (["input", "select", "textarea", "button", "a", "summary", "details", "label"].includes(tag)) return true;
  try {
    return Boolean(node.closest("input,select,textarea,button,a,summary,details,label"));
  } catch {
    return false;
  }
}

// Manual feedback UX: map task direction -> expected unit defaults.
const RT_RULES = {
  HER: { unitDefault: "mV", conditionDefault: "10 mA cm-2", requireCondition: true, requireProduct: false },
  OER: { unitDefault: "mV", conditionDefault: "10 mA cm-2", requireCondition: true, requireProduct: false },
  ORR: { unitDefault: "V", conditionDefault: "", requireCondition: false, requireProduct: false },
  HOR: { unitDefault: "mA cm-2", conditionDefault: "", requireCondition: false, requireProduct: false },
  UOR: { unitDefault: "V", conditionDefault: "10 mA cm-2", requireCondition: true, requireProduct: false },
  EOR: { unitDefault: "A mgmetal-1", conditionDefault: "", requireCondition: false, requireProduct: false },
  HZOR: { unitDefault: "mV", conditionDefault: "10 mA cm-2", requireCondition: true, requireProduct: false },
  O5H: { unitDefault: "%", conditionDefault: "", requireCondition: false, requireProduct: false },
  CO2RR: { unitDefault: "%", conditionDefault: "", requireCondition: false, requireProduct: true },
  photothermal_conversion_efficiency: { unitDefault: "%", conditionDefault: "", requireCondition: false, requireProduct: false },
  conductivity: { unitDefault: "S/m", conditionDefault: "", requireCondition: false, requireProduct: false },
  thermal_conductivity: { unitDefault: "W m-1 K-1", conditionDefault: "", requireCondition: false, requireProduct: false },
  ferromagnetism: { unitDefault: "emu/g", conditionDefault: "", requireCondition: false, requireProduct: false },
  ferrimagnetism: { unitDefault: "emu/g", conditionDefault: "", requireCondition: false, requireProduct: false },
  antiferromagnetism: { unitDefault: "K", conditionDefault: "", requireCondition: false, requireProduct: false },
  photocatalytic_h2o2: { unitDefault: "%", conditionDefault: "", requireCondition: false, requireProduct: false },
  antibacterial: { unitDefault: "ppm", conditionDefault: "", requireCondition: false, requireProduct: false },
  thermoelectric: { unitDefault: "dimensionless", conditionDefault: "", requireCondition: false, requireProduct: false },
  furfural_hydrogenation: { unitDefault: "%", conditionDefault: "", requireCondition: false, requireProduct: false },
};

const CO2RR_PRODUCTS = ["CO", "HCOOH", "CH4", "C2H5OH", "C2H4", "CH3COOH"];

let manualRecoList = []; // list from /api/recommendations (completed, non-deleted)
let manualRecoJobCache = {}; // job_id -> /api/jobs/{id} payload (best-effort)
let manualRecoResultCache = {}; // job_id -> /api/jobs/{id}/result payload (best-effort)
let jobLogCache = {}; // job_id -> /api/jobs/{id}/log payload (best-effort)

let manualGroupCounter = 0;
let manualGroups = []; // ordered list of group_ids
let manualGroupStates = {}; // group_id -> state
let manualActiveGroupId = null;

let recoSuggestTimer = null;
let recoSuggestSeq = 0;

let analysisCache = null; // { overall, rounds, records }
let experienceCurrentCache = null; // { raw, guidelines }

function manualDraftKey(recoJobId) {
  return `${STORAGE.manual_draft_prefix}${String(recoJobId || "").trim()}`;
}

const FEEDBACK_MATERIAL_FIELDS = [
  "material_serial_no",
  "material_name",
  "major_category",
  "components",
  "structure_relationships",
  "precursors",
  "feed_ratio",
  "preparation_method",
  "elements",
  "element_content",
  "conditions",
  "custom_prompt",
];

const FEEDBACK_MATERIAL_SELECTORS = {
  material_serial_no: ".feedback-material-serial-no",
  material_name: ".feedback-material-name",
  major_category: ".feedback-major-category",
  components: ".feedback-components",
  structure_relationships: ".feedback-structure-relationships",
  precursors: ".feedback-precursors",
  feed_ratio: ".feedback-feed-ratio",
  preparation_method: ".feedback-preparation-method",
  elements: ".feedback-elements",
  element_content: ".feedback-element-content",
  conditions: ".feedback-conditions",
  custom_prompt: ".feedback-custom-prompt",
};

// Serial numbers are user-facing stable labels. Keep them as ordinary safe
// integers in the browser while allowing the field to remain optional for
// legacy records that never had a serial number.
function normalizeMaterialSerial(value) {
  const text = String(value ?? "").trim();
  if (!text) return null;
  if (!/^\d+$/.test(text)) return null;
  const number = Number(text);
  return Number.isSafeInteger(number) && number >= 1 ? number : null;
}

function materialSerialFromValue(value, fallback = null) {
  const source = value && typeof value === "object" ? value : {};
  const payload = source.payload && typeof source.payload === "object" ? source.payload : {};
  const nested = source.material_input && typeof source.material_input === "object"
    ? source.material_input
    : payload.material_input && typeof payload.material_input === "object"
      ? payload.material_input
      : {};
  const raw = source.material_serial_no ?? payload.material_serial_no ?? nested.material_serial_no;
  return normalizeMaterialSerial(raw) ?? fallback;
}

function splitFeedbackList(value) {
  return String(value || "")
    .split(/[,，;；、]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function cleanFeedbackMaterialInput(value) {
  const source = value && typeof value === "object" ? value : {};
  const out = {};
  for (const key of FEEDBACK_MATERIAL_FIELDS) {
    const raw = source[key];
    const cleaned = key === "material_serial_no"
      ? normalizeMaterialSerial(raw)
      : Array.isArray(raw)
      ? raw.map((item) => String(item || "").trim()).filter(Boolean)
      : String(raw ?? "").trim();
    if (Array.isArray(cleaned) ? cleaned.length : cleaned) out[key] = cleaned;
  }
  return out;
}

function recommendationMaterialInputDefaults(recoItem, recoJob) {
  const payload = recoJob && typeof recoJob === "object" ? recoJob.payload || {} : {};
  const nested = payload.material_input && typeof payload.material_input === "object" ? payload.material_input : {};
  const listed = recoItem?.material_input && typeof recoItem.material_input === "object" ? recoItem.material_input : {};
  const materialName = String(payload.material_name || recoItem?.material_name || nested.material_name || listed.material_name || "").trim();
  return cleanFeedbackMaterialInput({
    ...listed,
    ...nested,
    ...(listed.material_serial_no == null && nested.material_serial_no == null && payload.material_serial_no != null
      ? { material_serial_no: payload.material_serial_no }
      : {}),
    ...(materialName ? { material_name: materialName } : {}),
  });
}

function materialNameFromRecommendation(value) {
  const source = value && typeof value === "object" ? value : {};
  const payload = source.payload && typeof source.payload === "object" ? source.payload : {};
  const materialInput = source.material_input && typeof source.material_input === "object"
    ? source.material_input
    : payload.material_input && typeof payload.material_input === "object"
      ? payload.material_input
      : {};
  return String(source.material_name || payload.material_name || materialInput.material_name || "").trim();
}

function legacyMaterialRecordLabel() {
  return getLang() === "zh" ? "旧版元素记录（无材料名称）" : "Legacy element record (no material name)";
}

function recommendationMaterialDisplayName(value) {
  return materialNameFromRecommendation(value) || legacyMaterialRecordLabel();
}

function materialInputFromJob(job) {
  const source = job && typeof job === "object" ? job : {};
  const payload = job && typeof job === "object" ? job.payload || {} : {};
  const nested = payload.material_input && typeof payload.material_input === "object" ? payload.material_input : {};
  const listed = source.material_input && typeof source.material_input === "object" ? source.material_input : {};
  const materialName = String(source.material_name || payload.material_name || listed.material_name || nested.material_name || "").trim();
  return cleanFeedbackMaterialInput({
    ...listed,
    ...nested,
    ...(listed.material_serial_no == null && nested.material_serial_no == null && source.material_serial_no == null && payload.material_serial_no != null
      ? { material_serial_no: payload.material_serial_no }
      : source.material_serial_no != null && listed.material_serial_no == null && nested.material_serial_no == null
        ? { material_serial_no: source.material_serial_no }
      : {}),
    ...(payload.custom_prompt && !nested.custom_prompt ? { custom_prompt: payload.custom_prompt } : {}),
    ...(materialName ? { material_name: materialName } : {}),
  });
}

function hasStructuredMaterialFields(materialInput) {
  const material = cleanFeedbackMaterialInput(materialInput);
  return FEEDBACK_MATERIAL_FIELDS.some(
    (key) => key !== "material_name" && key !== "custom_prompt" && material[key] != null
  );
}

function loadManualDraftBundle(recoJobId) {
  const jobId = String(recoJobId || "").trim();
  if (!jobId) return { rows: [], material_input: {}, schema_version: 0 };
  try {
    const raw = localStorage.getItem(manualDraftKey(jobId));
    if (!raw) return { rows: [], material_input: {}, schema_version: 0 };
    const obj = JSON.parse(raw);
    const rows = Array.isArray(obj?.rows) ? obj.rows : Array.isArray(obj) ? obj : [];
    const safeRows = rows.filter((r) => r && typeof r === "object");
    const materialInput = cleanFeedbackMaterialInput(obj?.material_input);
    const schemaVersion = Number.isInteger(obj?.schema_version) ? obj.schema_version : 0;
    return { rows: safeRows, material_input: materialInput, schema_version: schemaVersion };
  } catch {
    return { rows: [], material_input: {}, schema_version: 0 };
  }
}

function saveManualDraftBundle(recoJobId, { rows, material_input: materialInput } = {}) {
  const jobId = String(recoJobId || "").trim();
  if (!jobId) return;
  const safeRows = Array.isArray(rows) ? rows.filter((r) => r && typeof r === "object") : [];
  const safeMaterialInput = cleanFeedbackMaterialInput(materialInput);
  try {
    localStorage.setItem(
      manualDraftKey(jobId),
      JSON.stringify({
        schema_version: MANUAL_DRAFT_SCHEMA_VERSION,
        rows: safeRows,
        material_input: safeMaterialInput,
        saved_at_utc: new Date().toISOString(),
      })
    );
  } catch {
    // ignore (storage quota / privacy mode)
  }
}

function clearManualDraft(recoJobId) {
  const jobId = String(recoJobId || "").trim();
  if (!jobId) return;
  try {
    localStorage.removeItem(manualDraftKey(jobId));
  } catch {}
}

function getLang() {
  const saved = localStorage.getItem(STORAGE.lang);
  if (saved === "zh" || saved === "en") return saved;
  const nav = (navigator.language || "").toLowerCase();
  return nav.startsWith("zh") ? "zh" : "en";
}

function reactionLabel(key) {
  const rt = REACTION_TYPES.find((x) => x.key === key);
  if (!rt) return String(key || "");
  return getLang() === "zh" ? rt.zh : rt.en;
}

function renderTaskOverview() {
  const taskSelect = document.getElementById("recommend-task-type");
  if (taskSelect) {
    const current = taskSelect.value || "__all__";
    const allLabel = getLang() === "zh" ? `全部 ${REACTION_TYPES.length} 个方向（外层分别辩论后排序）` : `All ${REACTION_TYPES.length} directions (independent debates + ranking)`;
    taskSelect.innerHTML = [
      `<option value="__all__">${escapeHtml(allLabel)}</option>`,
      ...REACTION_TYPES.map((item) => `<option value="${escapeHtml(item.key)}">${escapeHtml(reactionLabel(item.key))}</option>`),
    ].join("");
    taskSelect.value = REACTION_TYPES.some((item) => item.key === current) ? current : "__all__";
  }
  const box = document.getElementById("task-overview");
  if (!box) return;
  const lang = getLang();
  const renderGroup = (titleZh, titleEn, items, family) => `
    <div class="task-overview-group ${family}">
      <div class="task-overview-title">${escapeHtml(lang === "zh" ? titleZh : titleEn)}</div>
      <div class="task-chip-row">
        ${items
          .map((x) => `<span class="task-chip ${family}" title="${escapeHtml(x.key)}">${escapeHtml(reactionLabel(x.key))}</span>`)
          .join("")}
      </div>
    </div>
  `;
  box.innerHTML = `
    <div class="task-overview-head">
      <span>${escapeHtml(lang === "zh" ? "统一排序池" : "Unified ranking pool")}</span>
      <code>${REACTION_TYPES.length} ${escapeHtml(lang === "zh" ? "个方向" : "directions")}</code>
    </div>
    <div class="task-overview-grid">
      ${renderGroup("反应方向（经验/RAG 按 reaction 硬过滤）", "Reaction tasks (experience/RAG hard-filtered as reaction)", REACTION_TASK_TYPES, "reaction")}
      ${renderGroup("材料性能方向（经验/RAG 按 material_property 硬过滤）", "Material-property tasks (experience/RAG hard-filtered as material_property)", MATERIAL_PROPERTY_TYPES, "material")}
    </div>
    <div class="hint muted">${escapeHtml(
      lang === "zh"
        ? "每个方向运行一场独立四智能体辩论，再按各方向自身标尺得到的标准化评分汇总排序，默认 Top 2。"
        : "Each direction runs an independent four-agent debate, then task-specific normalized scores are ranked; Top 2 by default."
    )}</div>
  `;
}

function canonicalRt(rt) {
  const s = String(rt || "").trim();
  if (!s) return "";
  if (REACTION_TYPES.some((x) => x.key === s)) return s;
  const up = s.toUpperCase();
  if (REACTION_TYPES.some((x) => x.key === up)) return up;
  const low = s.toLowerCase().replace(/[\s-]+/g, "_");
  if (low === "hydrogen_evolution" || low === "hydrogen_evolution_reaction") return "HER";
  if (low === "oxygen_evolution" || low === "oxygen_evolution_reaction") return "OER";
  if (low === "oxygen_reduction" || low === "oxygen_reduction_reaction") return "ORR";
  if (low === "hydrogen_oxidation" || low === "hydrogen_oxidation_reaction") return "HOR";
  if (low === "urea_oxidation" || low === "urea_oxidation_reaction") return "UOR";
  if (low === "ethanol_oxidation" || low === "ethanol_oxidation_reaction") return "EOR";
  if (low === "hydrazine_oxidation" || low === "hydrazine_oxidation_reaction") return "HZOR";
  if (low === "co2_reduction" || low === "co2_reduction_reaction" || low === "carbon_dioxide_reduction") return "CO2RR";
  if (low === "photothermal" || low === "photothermal_conversion_efficiency") return "photothermal_conversion_efficiency";
  if (low === "electrical_conductivity" || low === "conductivity") return "conductivity";
  if (low === "thermal_conductivity") return "thermal_conductivity";
  if (low === "ferromagnetic" || low === "ferromagnetism") return "ferromagnetism";
  if (low === "ferrimagnetic" || low === "ferrimagnetism") return "ferrimagnetism";
  if (low === "anti_ferromagnetism" || low === "anti_ferromagnetic" || low === "antiferromagnetic" || low === "antiferromagnetism") {
    return "antiferromagnetism";
  }
  if (low === "photocatalytic_h2o2" || low === "photocatalytic_hydrogen_peroxide") return "photocatalytic_h2o2";
  if (low === "antibacterial" || low === "antimicrobial") return "antibacterial";
  if (low === "thermoelectric" || low === "zt") return "thermoelectric";
  if (low === "furfural_hydrogenation" || low === "furfuryl_alcohol") return "furfural_hydrogenation";
  return "";
}

function refreshManualReactionSelectLabels() {
  document.querySelectorAll("select.manual-rt").forEach((sel) => {
    const val = sel.value;
    sel.innerHTML = REACTION_TYPES.map((x) => `<option value="${x.key}">${escapeHtml(reactionLabel(x.key))}</option>`).join("");
    sel.value = val;
  });
}

function setLang(lang) {
  localStorage.setItem(STORAGE.lang, lang);
  document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  applyI18n();
  updateRecommendMaterialCardLabels();
  updateRecommendCountSummary();
  refreshManualReactionSelectLabels();
  // Re-render dynamic blocks that contain localized labels.
  try {
    renderRecoOptionsForAllManualGroups();
    renderAllManualGroupSummaries();
    updateAllManualGroupMetas();
    for (const gid of manualGroups) updateManualGroupMaterialPreview(manualGroupStates[gid]);
  } catch {}
  renderExperienceHistory(); // re-render labels
  renderExperienceCurrent(); // update guideline labels
  refreshHistoryRecommendations(); // re-render table labels
  renderAnalysisControls(); // update option labels
  renderAnalysisFromCache(); // re-render chart with localized hints
}

function getTheme() {
  const saved = localStorage.getItem(STORAGE.theme);
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function clampInt(x, lo, hi) {
  const n = Number.parseInt(String(x), 10);
  if (!Number.isFinite(n)) return lo;
  return Math.max(lo, Math.min(hi, n));
}

function getAnalysisAggKind() {
  const saved = localStorage.getItem(STORAGE.analysis_agg_kind);
  if (saved === "rounds" || saved === "records_bucket" || saved === "records_cumulative") return saved;
  // Default: record-based buckets aligned with the selected feedback batch size.
  return "records_bucket";
}

function setAnalysisAggKind(kind) {
  const v = String(kind || "").trim();
  if (!v) return;
  localStorage.setItem(STORAGE.analysis_agg_kind, v);
}

function getAnalysisAggStep() {
  return clampInt(localStorage.getItem(STORAGE.analysis_agg_step) || String(FIXED_UPDATE_BATCH_SIZE), 1, 200);
}

function setAnalysisAggStep(step) {
  localStorage.setItem(STORAGE.analysis_agg_step, String(clampInt(step, 1, 200)));
}

const EXPERIENCE_PAGE_SIZES = [10, 20, 30, 50, 100];

function getExperiencePageSize() {
  const raw = localStorage.getItem(STORAGE.experience_page_size) || "30";
  const n = clampInt(raw, 5, 500);
  return EXPERIENCE_PAGE_SIZES.includes(n) ? n : 30;
}

function setExperiencePageSize(n) {
  const want = clampInt(n, 5, 500);
  const v = EXPERIENCE_PAGE_SIZES.includes(want) ? want : 30;
  try {
    localStorage.setItem(STORAGE.experience_page_size, String(v));
  } catch {}
}

function getExperiencePage() {
  return clampInt(localStorage.getItem(STORAGE.experience_page) || "1", 1, 999999);
}

function setExperiencePage(p) {
  try {
    localStorage.setItem(STORAGE.experience_page, String(clampInt(p, 1, 999999)));
  } catch {}
}

function setTheme(theme) {
  localStorage.setItem(STORAGE.theme, theme);
  document.documentElement.dataset.theme = theme;
  updateThemeButton();
}

function t(key) {
  const lang = getLang();
  return (I18N[lang] && I18N[lang][key]) || (I18N.en && I18N.en[key]) || key;
}

function applyI18n() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (!key) return;
    // theme toggle is dynamic
    if (key === "theme_toggle") return;
    el.textContent = t(key);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.getAttribute("data-i18n-placeholder");
    if (!key) return;
    el.setAttribute("placeholder", t(key));
  });
  updateThemeButton();
  renderTaskOverview();
}

function updateThemeButton() {
  const btn = document.getElementById("theme-toggle");
  if (!btn) return;
  const theme = getTheme();
  btn.textContent = theme === "dark" ? t("theme_toggle_dark") : t("theme_toggle_light");
}

const ACTIVE_JOB_STATUSES = new Set(["queued", "running", "cancelling"]);

function isActiveJobStatus(status) {
  return ACTIVE_JOB_STATUSES.has(String(status || "").toLowerCase());
}

function syncJobRunningIndicator(container, status, textElement = null, text = undefined) {
  const active = isActiveJobStatus(status);
  if (container) {
    container.classList.toggle("hidden", !active);
    container.hidden = !active;
    container.setAttribute("aria-hidden", active ? "false" : "true");
    container.setAttribute("aria-busy", active ? "true" : "false");
  }
  if (textElement && text !== undefined) textElement.textContent = String(text ?? "");
  return active;
}

function pill(status) {
  const s = String(status || "").toLowerCase();
  if (s === "completed") return `<span class="pill ok">${t("completed_prefix")}</span>`;
  if (s === "failed") return `<span class="pill bad">${t("failed_prefix")}</span>`;
  if (s === "queued") return `<span class="pill run">${t("queued_prefix")}</span>`;
  if (s === "running") return `<span class="pill run">${t("running_prefix")}</span>`;
  if (s === "cancelling") return `<span class="pill run">${t("cancelling_prefix")}</span>`;
  if (s === "cancelled" || s === "canceled") return `<span class="pill neutral">${t("cancelled_prefix")}</span>`;
  if (s === "prepared") return `<span class="pill ok">${t("prepared_prefix")}</span>`;
  return `<span class="pill">${status}</span>`;
}

function fmtBeijing(iso) {
  if (!iso) return "N/A";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  const lang = getLang() === "zh" ? "zh-CN" : "en";
  return new Intl.DateTimeFormat(lang, {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(d);
}

function fmtDurationSeconds(value) {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric < 0) return "—";
  const total = Math.floor(numeric);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const units = getLang() === "zh" ? ["小时", "分", "秒"] : ["h", "m", "s"];
  if (hours) return `${hours}${units[0]} ${minutes}${units[1]} ${seconds}${units[2]}`;
  if (minutes) return `${minutes}${units[1]} ${seconds}${units[2]}`;
  return `${seconds}${units[2]}`;
}

function durationSecondsForJob(job, nowMs = Date.now()) {
  const persisted = job?.duration_seconds;
  if (persisted !== null && persisted !== undefined && persisted !== "") {
    const numeric = Number(persisted);
    if (Number.isFinite(numeric) && numeric >= 0) return numeric;
  }
  const startedMs = Date.parse(String(job?.started_at_utc || ""));
  if (!Number.isFinite(startedMs)) return null;
  const finishedMs = Date.parse(String(job?.finished_at_utc || ""));
  const endMs = Number.isFinite(finishedMs) ? finishedMs : nowMs;
  return Math.max(0, (endMs - startedMs) / 1000);
}

function escapeHtml(s) {
  return String(s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function parseJsonMaybe(text) {
  const s = String(text ?? "").trim();
  if (!s) return null;
  try {
    const obj = JSON.parse(s);
    return obj && typeof obj === "object" ? obj : null;
  } catch {
    return null;
  }
}

async function apiJson(path, options = {}) {
  const resp = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const text = await resp.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!resp.ok) {
    let msg = data && data.error ? data.error : typeof data === "string" && data ? data : `HTTP ${resp.status}`;
    if (resp.status === 401) {
      msg =
        getLang() === "zh"
          ? `未授权 (401)：${msg || "unauthorized"}。如果你设置了 CHEMCOUNCIL_API_TOKEN，则需要在请求里带 Authorization: Bearer <token>。`
          : `Unauthorized (401): ${msg || "unauthorized"}. If CHEMCOUNCIL_API_TOKEN is set, requests must include Authorization: Bearer <token>.`;
    }
    throw new Error(msg);
  }
  return data;
}

async function apiText(path) {
  const resp = await fetch(path);
  const text = await resp.text();
  if (!resp.ok) throw new Error(text || `HTTP ${resp.status}`);
  return text;
}

function extractUniqueElements(text) {
  const matches = String(text || "").match(/[A-Z][a-z]?/g) || [];
  const uniq = [];
  for (const m of matches) {
    if (!uniq.includes(m)) uniq.push(m);
  }
  return uniq;
}

function inferRecommendMetalsScope(uniqCount) {
  const count = Number(uniqCount || 0);
  if (count >= 1) return "reported_elements";
  return "unknown";
}

function updateComponentsValidate() {
  const cards = [...document.querySelectorAll(".recommend-material-card")];
  if (cards.length) {
    cards.forEach((card) => updateRecommendMaterialValidation(card));
    return;
  }
  // Compatibility fallback for a stale page bundle that still has the legacy single input.
  const input = document.getElementById("recommend-material-name");
  const box = document.getElementById("components-validate");
  if (!input || !box) return;
  box.innerHTML = input.value.trim() ? `<span class="pill ok">OK</span>` : "";
}

function recommendFieldText(card, field) {
  const input = card?.querySelector(`[data-recommend-field="${field}"]`);
  return String(input?.value || "").trim();
}

function readRecommendMaterialCard(card) {
  const materialInput = {};
  const serialRaw = recommendFieldText(card, "material_serial_no");
  if (serialRaw) materialInput.material_serial_no = normalizeMaterialSerial(serialRaw) ?? serialRaw;
  const materialName = recommendFieldText(card, "material_name");
  if (materialName) materialInput.material_name = materialName;

  for (const field of RECOMMEND_MATERIAL_TEXT_FIELDS) {
    const value = recommendFieldText(card, field);
    if (value) materialInput[field] = value;
  }

  for (const field of ["precursors", "elements"]) {
    const values = recommendFieldText(card, field)
      .split(/[,，;；、]+/)
      .map((item) => item.trim())
      .filter(Boolean);
    if (values.length) materialInput[field] = values;
  }
  return materialInput;
}

function snapshotRecommendMaterialDrafts() {
  const cards = [...document.querySelectorAll(".recommend-material-card")];
  cards.forEach((card) => {
    const index = Number(card.getAttribute("data-recommend-index"));
    if (Number.isInteger(index) && index >= 0) recommendMaterialDrafts[index] = readRecommendMaterialCard(card);
  });
}

function recommendDraftValue(draft, field) {
  const raw = draft?.[field];
  if (Array.isArray(raw)) return raw.join(", ");
  return String(raw ?? "");
}

function updateRecommendMaterialValidation(card) {
  const input = card?.querySelector('[data-recommend-field="material_name"]');
  const box = card?.querySelector("[data-recommend-validation]");
  if (!input || !box) return;
  const hasName = Boolean(String(input.value || "").trim());
  box.innerHTML = hasName ? `<span class="pill ok">OK</span>` : "";
  input.setCustomValidity(hasName ? "" : getLang() === "zh" ? "材料名称为必填项。" : "Material name is required.");
  const serialInput = card?.querySelector('[data-recommend-field="material_serial_no"]');
  if (serialInput) {
    const serialRaw = String(serialInput.value || "").trim();
    const serialOk = !serialRaw || normalizeMaterialSerial(serialRaw) != null;
    serialInput.setCustomValidity(
      serialOk ? "" : getLang() === "zh" ? "材料序号必须是大于等于 1 的正整数。" : "Serial number must be a positive integer."
    );
  }
}

function updateRecommendMaterialCardLabels() {
  document.querySelectorAll(".recommend-material-card").forEach((card) => {
    const index = Number(card.getAttribute("data-recommend-index"));
    const title = card.querySelector("[data-recommend-card-title]");
    const number = card.querySelector("[data-recommend-card-number]");
    if (!Number.isInteger(index)) return;
    const serialRaw = recommendFieldText(card, "material_serial_no");
    const serial = normalizeMaterialSerial(serialRaw) ?? index + 1;
    if (title) title.textContent = `${t("recommend_material_card_title")} ${index + 1}`;
    if (number) number.textContent = `#${serial}`;
  });
}

function updateRecommendCountSummary() {
  const summary = document.getElementById("recommend-count-summary");
  if (!summary) return;
  const countText = getLang() === "zh" ? `当前填写 ${recommendMaterialCount} 条材料。` : `${recommendMaterialCount} material(s) selected.`;
  summary.textContent = `${t("recommend_material_count_hint")} ${countText}`;
}

function renderRecommendMaterialInputs(rawCount = 1) {
  const list = document.getElementById("recommend-material-list");
  if (!list) return;

  snapshotRecommendMaterialDrafts();
  const count = clampInt(rawCount, 1, MAX_RECOMMEND_MATERIALS);
  recommendMaterialCount = count;
  while (recommendMaterialDrafts.length < count) recommendMaterialDrafts.push({});

  const inputValue = (draft, field) => escapeHtml(recommendDraftValue(draft, field));
  list.innerHTML = Array.from({ length: count }, (_, index) => {
    const draft = recommendMaterialDrafts[index] || {};
    const serial = normalizeMaterialSerial(draft.material_serial_no) ?? index + 1;
    return `
      <article class="card small recommend-material-card" data-recommend-index="${index}">
        <div class="recommend-material-card-head">
          <div>
            <div class="recommend-material-card-title" data-recommend-card-title></div>
            <div class="hint muted" data-i18n="recommend_material_card_hint"></div>
          </div>
          <span class="pill neutral" data-recommend-card-number>#${index + 1}</span>
        </div>
        <label class="recommend-material-serial-field">
          <span data-i18n="material_serial_no_label"></span>
          <input data-recommend-field="material_serial_no" type="number" min="1" step="1" inputmode="numeric" value="${escapeHtml(String(serial))}" />
          <div class="hint muted" data-i18n="material_serial_no_hint"></div>
        </label>
        <label>
          <span data-i18n="material_name_label"></span>
          <input data-recommend-field="material_name" type="text" required data-i18n-placeholder="material_name_placeholder" value="${inputValue(draft, "material_name")}" />
          <div class="hint" data-recommend-validation></div>
        </label>
        <label>
          <span data-i18n="custom_prompt_label"></span>
          <textarea data-recommend-field="custom_prompt" rows="4" data-i18n-placeholder="custom_prompt_placeholder">${inputValue(draft, "custom_prompt")}</textarea>
          <div class="hint muted" data-i18n="custom_prompt_hint"></div>
        </label>
        <details class="details">
          <summary data-i18n="structured_material_fields"></summary>
          <div class="row">
            <label class="grow"><span data-i18n="major_category_label"></span><input data-recommend-field="major_category" type="text" value="${inputValue(draft, "major_category")}" /></label>
            <label class="grow"><span data-i18n="material_components_label"></span><input data-recommend-field="components" type="text" value="${inputValue(draft, "components")}" /></label>
          </div>
          <label><span data-i18n="structure_relationships_label"></span><input data-recommend-field="structure_relationships" type="text" value="${inputValue(draft, "structure_relationships")}" /></label>
          <div class="row">
            <label class="grow"><span data-i18n="precursors_label"></span><input data-recommend-field="precursors" type="text" value="${inputValue(draft, "precursors")}" /></label>
            <label class="grow"><span data-i18n="feed_ratio_label"></span><input data-recommend-field="feed_ratio" type="text" value="${inputValue(draft, "feed_ratio")}" /></label>
          </div>
          <label><span data-i18n="preparation_method_label"></span><input data-recommend-field="preparation_method" type="text" value="${inputValue(draft, "preparation_method")}" /></label>
          <div class="row">
            <label class="grow"><span data-i18n="elements_label"></span><input data-recommend-field="elements" type="text" value="${inputValue(draft, "elements")}" /></label>
            <label class="grow"><span data-i18n="element_content_label"></span><input data-recommend-field="element_content" type="text" value="${inputValue(draft, "element_content")}" /></label>
          </div>
          <label><span data-i18n="conditions_label"></span><input data-recommend-field="conditions" type="text" value="${inputValue(draft, "conditions")}" /></label>
        </details>
      </article>
    `;
  }).join("");

  list.querySelectorAll(".recommend-material-card").forEach((card) => {
    const index = Number(card.getAttribute("data-recommend-index"));
    const sync = () => {
      recommendMaterialDrafts[index] = readRecommendMaterialCard(card);
      updateRecommendMaterialValidation(card);
      updateRecommendMaterialCardLabels();
    };
    card.querySelectorAll("input, textarea").forEach((input) => {
      input.addEventListener("input", sync);
      input.addEventListener("change", sync);
    });
    updateRecommendMaterialValidation(card);
  });
  updateRecommendMaterialCardLabels();
  updateRecommendCountSummary();
  applyI18n();
}

function recommendBatchProgressText(done, total) {
  const template = t("recommend_batch_progress");
  return template.replace("{done}", String(done)).replace("{total}", String(total));
}

function renderRecommendBatchResult(entries, submittedCount) {
  const allEntries = Array.isArray(entries) ? entries : [];
  const completed = allEntries.filter((entry) => entry?.job?.status === "completed");
  const failed = allEntries.filter((entry) => entry?.job?.status !== "completed");
  const total = Math.max(Number(submittedCount || 0), allEntries.length);
  const summaryStatus = failed.length ? "failed" : "completed";
  const cards = allEntries
    .map((entry, index) => {
      const name = String(entry?.materialInput?.material_name || `${t("recommend_material_card_title")} ${index + 1}`).trim();
      const serial = materialSerialFromValue(entry?.materialInput, index + 1);
      const jobId = String(entry?.jobId || entry?.job?.id || "").trim();
      const isComplete = entry?.job?.status === "completed" && entry?.resultPayload;
      const body = isComplete
        ? renderRankResult(jobId, entry.resultPayload, entry.job)
        : `<div class="pill bad">${escapeHtml(t("recommend_batch_failed_item"))}</div><div class="muted">${escapeHtml(String(entry?.error || entry?.job?.error || "—"))}</div>`;
      return `
        <details class="details recommend-batch-item" ${index === 0 ? "open" : ""}>
          <summary><b>#${escapeHtml(String(serial))} ${escapeHtml(name)}</b><span class="muted">${escapeHtml(isComplete ? t("completed_prefix") : t("failed_prefix"))}</span></summary>
          <div class="recommend-batch-item-body">${body}</div>
        </details>
      `;
    })
    .join("");

  return `
    <div class="row">
      ${pill(summaryStatus)}
      <b>${escapeHtml(t("recommend_batch_result_title"))}</b>
      <span class="muted">${escapeHtml(recommendBatchProgressText(completed.length, total))}</span>
    </div>
    <div class="recommend-batch-results">${cards || `<div class="muted">${escapeHtml(t("recommend_batch_empty"))}</div>`}</div>
  `;
}

function updateRecommendBatchLog(entries) {
  const box = document.getElementById("recommend-log");
  if (!box) return;
  const blocks = (Array.isArray(entries) ? entries : [])
    .filter((entry) => entry?.jobId)
    .map((entry) => {
      const serial = materialSerialFromValue(entry.materialInput, Number(entry.index || 0) + 1);
      const name = String(entry.materialInput?.material_name || `#${serial}`);
      const log = String(entry.logText || "").trim();
      return `===== #${serial} ${name} (${entry.jobId}) =====\n${log || t("loading")}`;
    });
  box.textContent = blocks.join("\n\n") || t("empty");
}

function setExperienceBuildDefaultsFromMode() {
  const mode = String(document.getElementById("experience-build-mode")?.value || "prepare_only");
  const truncate = document.getElementById("experience-build-truncate");
  const batch = document.getElementById("experience-build-batch");
  const grpoN = document.getElementById("experience-build-grpo-n");
  const conc = document.getElementById("experience-build-concurrency");
  const rag = document.getElementById("experience-build-rag");

  if (mode === "prepare_only") {
    if (truncate) truncate.value = "11291";
    if (batch) batch.value = "50";
    if (grpoN) grpoN.value = "1";
    if (conc) conc.value = "1";
    if (rag) rag.checked = false;
    return;
  }
  if (mode === "pilot") {
    if (truncate) truncate.value = "60";
    if (batch) batch.value = "10";
    if (grpoN) grpoN.value = "2";
    if (conc) conc.value = "1";
    if (rag) rag.checked = true;
    return;
  }
  if (truncate) truncate.value = "11291";
  if (batch) batch.value = "50";
  if (grpoN) grpoN.value = "3";
  if (conc) conc.value = "1";
  if (rag) rag.checked = true;
}

function renderExperienceBuildResult(jobId, payload) {
  const p = payload && typeof payload === "object" ? payload : {};
  const updated = p.updated_at_utc || null;
  const datasetRows = p.dataset_rows != null ? String(p.dataset_rows) : "N/A";
  const mode = String(p.mode || "N/A");
  const expName = String(p.exp_name || "N/A");
  const activePack = String(p.active_experience_yaml || "N/A");
  return `
    <div class="row">
      ${pill(mode === "prepare_only" ? "prepared" : "completed")}
      <b>${escapeHtml(
        mode === "prepare_only"
          ? getLang() === "zh"
            ? "统一经验库数据集已准备"
            : "Unified experience dataset prepared"
          : getLang() === "zh"
            ? "统一经验库流程完成"
            : "Unified experience flow completed"
      )}</b>
      <a class="secondary" href="/api/jobs/${encodeURIComponent(jobId)}/result" target="_blank" rel="noreferrer">${escapeHtml(t("download_json"))}</a>
      <a class="secondary" href="/api/experience/pack" target="_blank" rel="noreferrer">${escapeHtml(t("btn_download_current"))}</a>
    </div>
    <div class="stack">
      <div>${escapeHtml(t("job_id"))}=<code>${escapeHtml(jobId)}</code></div>
      <div>mode: <code>${escapeHtml(mode)}</code> · exp_name: <code>${escapeHtml(expName)}</code></div>
      <div>dataset: <code>${escapeHtml(String(p.dataset_name || "material_property_bal50_seed20260521"))}</code> · rows=<code>${escapeHtml(datasetRows)}</code></div>
      <div>active_experience_yaml: <code>${escapeHtml(activePack)}</code></div>
      <div>updated_at_utc: <code>${escapeHtml(updated || "N/A")}</code> · ${escapeHtml(t("beijing"))}: <code>${escapeHtml(updated ? fmtBeijing(updated) : "N/A")}</code></div>
      <div class="row">
        <a class="secondary" href="#recommend">${escapeHtml(getLang() === "zh" ? "去推荐排序" : "Go to recommendation ranking")}</a>
        <a class="secondary" href="#experience">${escapeHtml(getLang() === "zh" ? "查看经验库" : "View experience library")}</a>
      </div>
    </div>
  `;
}

function setActiveRoute(route) {
  const routes = ["recommend", "history", "feedback", "experience-build", "experience", "analysis"];
  const r = routes.includes(route) ? route : "recommend";
  routes.forEach((x) => {
    const page = document.getElementById(`page-${x}`);
    if (page) page.classList.toggle("hidden", x !== r);
  });
  document.querySelectorAll(".nav-link").forEach((a) => {
    a.classList.toggle("active", a.getAttribute("data-route") === r);
  });
}

function currentRoute() {
  const h = (window.location.hash || "").replace(/^#/, "");
  if (!h) return "recommend";
  if (h.startsWith("history")) return "history";
  if (h.startsWith("feedback")) return "feedback";
  if (h.startsWith("experience-build")) return "experience-build";
  if (h.startsWith("experience")) return "experience";
  if (h.startsWith("analysis")) return "analysis";
  return "recommend";
}

function csvEscape(v) {
  const s = String(v ?? "");
  if (s.includes('"')) return `"${s.replaceAll('"', '""')}"`;
  if (s.includes(",") || s.includes("\n") || s.includes("\r")) return `"${s}"`;
  return s;
}

function downloadText(filename, content, mime = "text/plain") {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function formatCompactNumber(value) {
  if (value == null || value === "") return "";
  const text = String(value).trim();
  if (!text) return "";
  const num = Number(text);
  if (!Number.isFinite(num)) return text;
  return String(num);
}

function normalizeCurrentDensityUnitText(unit) {
  const raw = String(unit || "").trim();
  if (!raw) return "";
  return raw
    .replace(/cm\^?-?2/gi, "cm-2")
    .replace(/cm²/gi, "cm-2")
    .replace(/\/\s*cm-?2/gi, " cm-2")
    .replace(/\s+/g, " ")
    .trim();
}

function formatValueWithUnit(value, unit) {
  if (value == null || value === "") return "";
  const valueText = formatCompactNumber(value);
  const unitText = String(unit || "").trim();
  return `${valueText}${unitText ? ` ${unitText}` : ""}`.trim();
}

function co2rrPredLineFromRankItem(it, metric) {
  const m = metric || {};
  const parts = [];
  const product = String(m.product || it?.final_products || it?.product || "").trim();
  if (product && product !== "N/A" && product !== "(missing)") {
    parts.push(`${getLang() === "zh" ? "产物" : "Product"}: ${product}`);
  }
  if (m.metric_value != null) {
    const label = String(m.metric_name || "").trim() || "FE";
    parts.push(`${label}: ${formatValueWithUnit(m.metric_value, m.metric_unit || "%")}`);
  } else if (it?.metric_value != null) {
    parts.push(`FE: ${formatValueWithUnit(it.metric_value, it.metric_unit || "%")}`);
  }
  if (m.partial_current_density != null) {
    const unit = normalizeCurrentDensityUnitText(m.partial_current_density_unit || "mA cm-2") || "mA cm-2";
    parts.push(`${getLang() === "zh" ? "部分电流密度" : "Partial current density"}: ${formatValueWithUnit(m.partial_current_density, unit)}`);
  }
  return parts.length ? parts.join(" · ") : "—";
}

function predLineFromRankItem(predItem, { includeCondition = true } = {}) {
  const it = predItem || null;
  const metric = it?.performance_evaluation || {};
  const rt = canonicalRt(it?.task_type || it?.reaction_type || it?.property_type);
  const rules = rt ? RT_RULES[rt] : null;
  const cond =
    includeCondition && rules?.requireCondition && rules?.conditionDefault
      ? getLang() === "zh"
        ? `（${String(rules.conditionDefault).trim()}）`
        : ` @ ${String(rules.conditionDefault).trim()}`
      : "";

  if (rt === "CO2RR") return co2rrPredLineFromRankItem(it, metric);
  if (metric.metric_value != null) return `${formatValueWithUnit(metric.metric_value, metric.metric_unit || "")}${cond}`.trim();
  if (it?.metric_value != null) return `${formatValueWithUnit(it.metric_value, it.metric_unit || "")}${cond}`.trim();
  return "—";
}

function predMapFromRankResult(resultPayload) {
  const predByRt = {};
  const ranking = Array.isArray(resultPayload?.ranking) ? resultPayload.ranking : [];
  for (const it of ranking) {
    const rt = canonicalRt(it?.task_type || it?.reaction_type || it?.property_type);
    if (!rt) continue;
    predByRt[rt] = it;
  }
  return predByRt;
}

function manualGroupsContainer() {
  return document.getElementById("manual-groups");
}

function getManualOpenRecoJobIds() {
  try {
    const raw = localStorage.getItem(STORAGE.manual_open_recos);
    if (!raw) return [];
    const obj = JSON.parse(raw);
    const ids = Array.isArray(obj) ? obj : Array.isArray(obj?.recos) ? obj.recos : [];
    return ids.map((x) => String(x || "").trim()).filter(Boolean);
  } catch {
    return [];
  }
}

function setManualOpenRecoJobIds(ids) {
  const out = (Array.isArray(ids) ? ids : []).map((x) => String(x || "").trim()).filter(Boolean);
  try {
    localStorage.setItem(STORAGE.manual_open_recos, JSON.stringify(out));
  } catch {}
}

function getManualActiveRecoJobId() {
  return String(localStorage.getItem(STORAGE.manual_active_reco) || "").trim() || null;
}

function setManualActiveRecoJobId(jobId) {
  const id = String(jobId || "").trim();
  try {
    if (!id) localStorage.removeItem(STORAGE.manual_active_reco);
    else localStorage.setItem(STORAGE.manual_active_reco, id);
  } catch {}
}

function persistManualGroupsToStorage() {
  const recos = manualGroups
    .map((gid) => manualGroupStates[gid]?.recoJobId || "")
    .map((x) => String(x || "").trim())
    .filter(Boolean);
  setManualOpenRecoJobIds(recos);
}

function isRecoJobIdUsed(jobId, { exceptGroupId = null } = {}) {
  const id = String(jobId || "").trim();
  if (!id) return false;
  for (const gid of manualGroups) {
    if (exceptGroupId && gid === exceptGroupId) continue;
    if (manualGroupStates[gid]?.recoJobId === id) return true;
  }
  return false;
}

function renderRecoOptionsForGroup(group) {
  const sel = group?.el?.querySelector("select.manual-group-reco");
  if (!sel) return;

  const cur = String(group.recoJobId || sel.value || "").trim();
  sel.innerHTML = "";

  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = getLang() === "zh" ? "请选择…" : "Select…";
  sel.appendChild(placeholder);

  for (const it of manualRecoList) {
    const opt = document.createElement("option");
    opt.value = it.job_id;
    const when = it.finished_at_utc || it.created_at_utc;
    const whenBj = when ? fmtBeijing(when) : "—";
    const materialName = recommendationMaterialDisplayName(it).replaceAll("\n", " ").trim();
    const taskItems = Array.isArray(it.task_types) ? it.task_types : [];
    const tasks = taskItems.length === 1
      ? reactionLabel(taskItems[0])
      : taskItems.length > 1
        ? getLang() === "zh"
          ? `${taskItems.length} 个方向`
          : `${taskItems.length} directions`
        : "";
    const short = materialName.length > 54 ? materialName.slice(0, 54) + "…" : materialName;
    const serial = materialSerialFromValue(it);
    opt.textContent = `${serial == null ? "" : `#${serial} · `}${whenBj} · ${short || "—"}${tasks ? ` · ${tasks}` : ""}`;
    sel.appendChild(opt);
  }

  // Ensure current selection stays visible even if filtered out / older than limit.
  if (cur && ![...sel.options].some((o) => o.value === cur)) {
    const opt = document.createElement("option");
    opt.value = cur;
    opt.textContent = cur;
    sel.appendChild(opt);
  }

  sel.value = cur;
}

function renderRecoOptionsForAllManualGroups() {
  for (const gid of manualGroups) renderRecoOptionsForGroup(manualGroupStates[gid]);
}

function setManualGroupActive(groupId) {
  const gid = String(groupId || "").trim();
  if (!gid || !manualGroupStates[gid]) return;
  manualActiveGroupId = gid;

  for (const g of manualGroups) {
    const st = manualGroupStates[g];
    st?.el?.classList?.toggle("active", g === gid);
  }

  const activeReco = manualGroupStates[gid]?.recoJobId || null;
  if (activeReco) setManualActiveRecoJobId(activeReco);
}

function getActiveManualGroup() {
  if (manualActiveGroupId && manualGroupStates[manualActiveGroupId]) return manualGroupStates[manualActiveGroupId];

  // Fallback: first group with a selected reco, else first group.
  for (const gid of manualGroups) {
    const st = manualGroupStates[gid];
    if (st?.recoJobId) return st;
  }
  return manualGroups.length ? manualGroupStates[manualGroups[0]] : null;
}

function isManualGroupMarkedForSubmit(group) {
  const cb = group?.el?.querySelector("input.manual-group-submit");
  return Boolean(cb && cb.checked);
}

function collectManualGroupsForSubmit() {
  ensureManualGroupsInitialized();
  const all = manualGroups.map((gid) => manualGroupStates[gid]).filter(Boolean);
  const checked = all.filter((g) => isManualGroupMarkedForSubmit(g));

  if (checked.length) {
    return { mode: "checked", groups: checked };
  }
  const active = getActiveManualGroup();
  return { mode: "active", groups: active ? [active] : [] };
}

function estimateManualGroupUpdateSize(group) {
  // In training-free GRPO, batch_size counts *training samples* (questions).
  const rows = Array.from(group?.el?.querySelectorAll("tbody.manual-group-rows tr") || []);
  let numRows = 0;
  let numSamplesEst = 0;
  for (const tr of rows) {
    const row = readManualRowFromDom(tr);
    if (!manualRowIsComplete(row)) continue;
    numRows += 1;
    numSamplesEst += 1;
  }
  return { numRows, numSamplesEst };
}

function manualRowIsComplete(row) {
  const taskType = canonicalRt(row?.task_type || row?.property_type || row?.reaction_type) || "";
  if (!taskType) return false;
  if (taskType === "CO2RR") {
    return Boolean(
      String(row?.product || "").trim() &&
        String(row?.faradaic_efficiency || "").trim() &&
        String(row?.partial_current_density || "").trim()
    );
  }
  return Boolean(String(row?.value || "").trim());
}

function readManualRowFromDom(tr) {
  const rt = canonicalRt(tr.querySelector(".manual-rt")?.value?.trim()) || DEFAULT_PROPERTY_TYPE;
  return {
    task_type: rt,
    property_type: rt,
    reaction_type: rt,
    value: tr.querySelector(".manual-value")?.value ?? "",
    unit: tr.querySelector(".manual-unit")?.value?.trim() || "",
    product: tr.querySelector(".manual-product")?.value?.trim() || "",
    faradaic_efficiency: tr.querySelector(".manual-fe")?.value ?? "",
    faradaic_efficiency_unit: "%",
    partial_current_density: tr.querySelector(".manual-partial-current")?.value ?? "",
    partial_current_density_unit: tr.querySelector(".manual-partial-unit")?.value?.trim() || "mA cm-2",
    condition: tr.querySelector(".manual-condition")?.value ?? "",
    notes: tr.querySelector(".manual-notes")?.value ?? "",
  };
}

function readManualGroupDraftFromDom(group) {
  const rows = Array.from(group?.el?.querySelectorAll("tbody.manual-group-rows tr") || []);
  return rows.map((tr) => readManualRowFromDom(tr));
}

function readManualGroupMaterialInputFromDom(group) {
  const materialInput = {};
  for (const key of FEEDBACK_MATERIAL_FIELDS) {
    const selector = FEEDBACK_MATERIAL_SELECTORS[key];
    const raw = group?.el?.querySelector(selector)?.value ?? "";
    const value = String(raw || "").trim();
    if (!value) continue;
    materialInput[key] = key === "material_serial_no"
      ? normalizeMaterialSerial(value) ?? value
      : key === "precursors" || key === "elements"
        ? splitFeedbackList(value)
        : value;
  }
  return cleanFeedbackMaterialInput(materialInput);
}

function writeManualGroupMaterialInputToDom(group, value) {
  const materialInput = cleanFeedbackMaterialInput(value);
  for (const key of FEEDBACK_MATERIAL_FIELDS) {
    const el = group?.el?.querySelector(FEEDBACK_MATERIAL_SELECTORS[key]);
    if (!el) continue;
    const raw = materialInput[key];
    el.value = Array.isArray(raw) ? raw.join(", ") : String(raw || "");
  }
  group.materialInput = materialInput;
}

function updateManualGroupMeta(group) {
  const meta = group?.el?.querySelector(".manual-group-meta");
  const clearBtn = group?.el?.querySelector("button.manual-group-clear-draft");
  if (clearBtn) clearBtn.disabled = false;
  if (!meta) return;

  const materialInput = readManualGroupMaterialInputFromDom(group);
  const serial = normalizeMaterialSerial(materialInput.material_serial_no);
  const materialName = String(materialInput.material_name || "").trim();
  const totalRows = Array.from(group?.el?.querySelectorAll("tbody.manual-group-rows tr") || []).length;
  const filled = estimateManualGroupUpdateSize(group);
  const warn = filled.numSamplesEst > 0 && filled.numSamplesEst < FIXED_UPDATE_BATCH_SIZE;
  const source = group?.recoJobId
    ? getLang() === "zh"
      ? "已关联历史推荐"
      : "Recommendation linked"
    : getLang() === "zh"
      ? "直接实验反馈"
      : "Direct lab feedback";
  const msg = getLang() === "zh"
    ? `${source}；序号：${serial == null ? "未填写" : serial}；材料：${materialName || "未填写"}。共 ${totalRows} 行，已完整填写 ${filled.numRows} 行，预计 ${filled.numSamplesEst} 条训练样本（batch_size=${FIXED_UPDATE_BATCH_SIZE}）。${warn ? `当前可作为不满批次运行；积累到 ${FIXED_UPDATE_BATCH_SIZE} 条可与测试配置完全对齐。` : ""}`
    : `${source}; serial: ${serial == null ? "missing" : serial}; material: ${materialName || "missing"}. ${totalRows} row(s), ${filled.numRows} complete, approximately ${filled.numSamplesEst} training sample(s) (batch_size=${FIXED_UPDATE_BATCH_SIZE}).${warn ? ` This can run as a partial batch; accumulate ${FIXED_UPDATE_BATCH_SIZE} samples to match the tested configuration.` : ""}`;
  meta.textContent = msg;
}

function updateAllManualGroupMetas() {
  for (const gid of manualGroups) updateManualGroupMeta(manualGroupStates[gid]);
}

function saveManualGroupDraftNow(groupId) {
  const gid = String(groupId || "").trim();
  const group = manualGroupStates[gid];
  if (!group) return;
  if (!group.recoJobId) {
    updateManualGroupMeta(group);
    return;
  }
  saveManualDraftBundle(group.recoJobId, {
    rows: readManualGroupDraftFromDom(group),
    material_input: readManualGroupMaterialInputFromDom(group),
  });
  updateManualGroupMeta(group);
}

function scheduleSaveManualGroupDraft(groupId) {
  const gid = String(groupId || "").trim();
  const group = manualGroupStates[gid];
  if (!group || group.suspendSave) return;
  if (group.saveTimer) clearTimeout(group.saveTimer);
  group.saveTimer = setTimeout(() => {
    group.saveTimer = null;
    saveManualGroupDraftNow(gid);
  }, 250);
}

function clearManualGroupRows(group) {
  const tbody = group?.el?.querySelector("tbody.manual-group-rows");
  if (!tbody) return;
  tbody.innerHTML = "";
}

function setManualSectionHidden(el, hidden) {
  if (!el) return;
  el.classList.toggle("hidden", !!hidden);
  el.hidden = !!hidden;
  if (hidden) {
    el.setAttribute("aria-hidden", "true");
    el.style.display = "none";
  } else {
    el.removeAttribute("aria-hidden");
    el.style.display = "";
  }
}

function syncManualRowByRt(tr, group, { resetDefaults = false } = {}) {
  const rt = canonicalRt(tr.querySelector(".manual-rt")?.value?.trim()) || DEFAULT_PROPERTY_TYPE;
  const rules = RT_RULES[rt] || RT_RULES[DEFAULT_PROPERTY_TYPE];
  const isCo2rr = rt === "CO2RR";
  tr.classList.toggle("manual-row-co2rr", isCo2rr);
  setManualSectionHidden(tr.querySelector(".manual-generic-fields"), isCo2rr);
  setManualSectionHidden(tr.querySelector(".manual-co2rr-fields"), !isCo2rr);

  const unitSel = tr.querySelector(".manual-unit");
  if (resetDefaults && unitSel && new Set(MATERIAL_UNIT_OPTIONS.map((x) => x.v)).has(rules.unitDefault || "")) {
    unitSel.value = rules.unitDefault || "S/m";
  }

  const condInput = tr.querySelector(".manual-condition");
  if (condInput) {
    const needCond = !!rules.requireCondition;
    condInput.readOnly = needCond;
    if (needCond && (resetDefaults || !condInput.value.trim())) condInput.value = rules.conditionDefault || "10 mA cm-2";
  }

  const predSpan = tr.querySelector(".manual-pred");
  if (predSpan) {
    const it = group?.predByRt?.[rt] || null;
    predSpan.textContent = predLineFromRankItem(it);
  }
}

function addManualRowToGroup(group, defaults = {}) {
  const tbody = group?.el?.querySelector("tbody.manual-group-rows");
  if (!tbody) return;

  const rt = canonicalRt(defaults.property_type || defaults.reaction_type) || DEFAULT_PROPERTY_TYPE;
  const rules = RT_RULES[rt] || RT_RULES[DEFAULT_PROPERTY_TYPE];
  const unit = defaults.unit || rules.unitDefault || "S/m";
  const condition = defaults.condition != null ? String(defaults.condition) : rules.conditionDefault || "";
  const valueText = defaults.value != null ? String(defaults.value) : "";
  const product = defaults.product != null ? String(defaults.product) : "CO";
  const faradaicEfficiency = defaults.faradaic_efficiency != null ? String(defaults.faradaic_efficiency) : "";
  const partialCurrent = defaults.partial_current_density != null ? String(defaults.partial_current_density) : "";
  const partialUnit = defaults.partial_current_density_unit != null ? String(defaults.partial_current_density_unit) : "mA cm-2";
  const notes = defaults.notes != null ? String(defaults.notes) : "";

  const pred = group?.predByRt?.[rt] || null;
  const metricLine = predLineFromRankItem(pred);

  const tr = document.createElement("tr");
  tr.className = "manual-row";
  tr.innerHTML = `
    <td class="manual-cell-rt">
      <select class="manual-rt">
        ${REACTION_TYPES.map((x) => `<option value="${x.key}" ${x.key === rt ? "selected" : ""}>${escapeHtml(reactionLabel(x.key))}</option>`).join("")}
      </select>
    </td>
    <td class="manual-cell-pred"><span class="manual-pred muted">${escapeHtml(metricLine)}</span></td>
    <td class="manual-cell-value">
      <div class="manual-generic-fields manual-inline-combo">
        <input class="manual-value" type="number" step="any" value="${escapeHtml(valueText)}" aria-label="${escapeHtml(getLang() === "zh" ? "实验值" : "Measured value")}" />
        <select class="manual-unit" aria-label="${escapeHtml(getLang() === "zh" ? "单位" : "Unit")}">
          ${MATERIAL_UNIT_OPTIONS.map((u) => `<option value="${u.v}" ${u.v === unit ? "selected" : ""}>${escapeHtml(u.label)}</option>`).join("")}
        </select>
      </div>
      <div class="manual-co2rr-fields manual-field-stack hidden">
        <div class="manual-field-row">
          <span class="manual-field-label">${escapeHtml(getLang() === "zh" ? "产物" : "Product")}</span>
          <select class="manual-product" aria-label="${escapeHtml(getLang() === "zh" ? "CO2RR 主要产物" : "CO2RR main product")}">
            ${CO2RR_PRODUCTS.map((item) => `<option value="${item}" ${item === product ? "selected" : ""}>${item}</option>`).join("")}
          </select>
        </div>
        <div class="manual-field-row">
          <span class="manual-field-label">FE</span>
          <input class="manual-fe" type="number" step="any" min="0" max="100" value="${escapeHtml(faradaicEfficiency)}" aria-label="${escapeHtml(getLang() === "zh" ? "法拉第效率" : "Faradaic efficiency")}" />
          <span class="manual-field-unit-badge">%</span>
        </div>
        <div class="manual-field-row">
          <span class="manual-field-label">j</span>
          <input class="manual-partial-current" type="number" step="any" value="${escapeHtml(partialCurrent)}" aria-label="${escapeHtml(getLang() === "zh" ? "部分电流密度" : "Partial current density")}" />
          <select class="manual-partial-unit" aria-label="${escapeHtml(getLang() === "zh" ? "部分电流密度单位" : "Partial current density unit")}">
            ${["mA cm-2", "A cm-2"].map((item) => `<option value="${item}" ${item === partialUnit ? "selected" : ""}>${item}</option>`).join("")}
          </select>
        </div>
      </div>
    </td>
    <td class="manual-cell-condition"><input class="manual-condition" type="text" value="${escapeHtml(condition)}" ${rules.requireCondition ? "readonly" : ""} /></td>
    <td class="manual-cell-product"><input class="manual-notes" type="text" value="${escapeHtml(notes)}" /></td>
    <td class="manual-cell-actions"><button type="button" class="secondary manual-del">×</button></td>
  `;
  tbody.appendChild(tr);

  tr.querySelector(".manual-del")?.addEventListener("click", () => {
    tr.remove();
    if (!tbody.querySelector("tr")) addManualRowToGroup(group);
    scheduleSaveManualGroupDraft(group.groupId);
  });

  const rtSelect = tr.querySelector(".manual-rt");
  rtSelect?.addEventListener("change", () => {
    syncManualRowByRt(tr, group, { resetDefaults: true });
    scheduleSaveManualGroupDraft(group.groupId);
  });

  const onAnyChange = () => {
    updateManualGroupMeta(group);
    scheduleSaveManualGroupDraft(group.groupId);
  };
  tr.querySelectorAll("input, select").forEach((input) => {
    input.addEventListener(input.tagName === "SELECT" ? "change" : "input", onAnyChange);
  });
  syncManualRowByRt(tr, group);
}

function pickTopReactionTypes(resultPayload, fallbackTopK = 2) {
  const top = Array.isArray(resultPayload?.top_k) ? resultPayload.top_k : [];
  const ranking = Array.isArray(resultPayload?.ranking) ? resultPayload.ranking : [];
  const rts = [];
  for (const it of top) {
    const rt = canonicalRt(it?.task_type || it?.reaction_type || it?.property_type);
    if (rt) rts.push(rt);
  }
  if (rts.length) return rts;
  // Fallback: take first K from ranking order.
  for (const it of ranking.slice(0, Math.max(1, fallbackTopK))) {
    const rt = canonicalRt(it?.task_type || it?.reaction_type || it?.property_type);
    if (rt) rts.push(rt);
  }
  return rts;
}

function renderManualGroupSummary(group) {
  const box = group?.el?.querySelector(".manual-group-summary");
  if (!box) return;
  const directMaterialInput = readManualGroupMaterialInputFromDom(group);
  const directSerial = normalizeMaterialSerial(directMaterialInput.material_serial_no);
  if (!group?.recoItem) {
    box.innerHTML = `<span class="pill neutral">${escapeHtml(
      getLang() === "zh" ? "直接实验反馈" : "Direct lab feedback"
    )}</span> <span class="muted">${escapeHtml(
      `${getLang() === "zh" ? "材料序号" : "Material serial"}: ${directSerial == null ? "—" : directSerial} · ${
        getLang() === "zh"
          ? "未关联历史推荐，不显示预测参考；材料真值仍可用于经验库更新。"
          : "No recommendation is linked, so no prediction reference is shown; measured values can still update the experience library."
      }`
    )}</span>`;
    return;
  }

  const recoItem = group.recoItem;
  const resultPayload = group.resultPayload || {};
  const finished = recoItem.finished_at_utc ? fmtBeijing(recoItem.finished_at_utc) : null;
  const created = recoItem.created_at_utc ? fmtBeijing(recoItem.created_at_utc) : null;
  const topRts = pickTopReactionTypes(resultPayload, recoItem.top_k_reactions || 2);
  const materialInput = readManualGroupMaterialInputFromDom(group);
  const materialName = String(materialInput.material_name || recoItem.material_name || "").trim();
  const serial = normalizeMaterialSerial(materialInput.material_serial_no ?? recoItem.material_serial_no);
  const materialDescription = materialName ? renderMaterialDescriptionPreview(materialInput) : "";

  box.innerHTML = `
    <div><span class="pill ok">${escapeHtml(getLang() === "zh" ? "已关联历史推荐" : "Recommendation linked")}</span> ${escapeHtml(t("job_id"))}=<code>${escapeHtml(recoItem.job_id)}</code></div>
    <div>${escapeHtml(t("finished_at"))}: <code>${escapeHtml(finished || created || "—")}</code></div>
    <div>${escapeHtml(getLang() === "zh" ? "材料序号" : "Material serial")}: <code>${escapeHtml(serial == null ? "—" : String(serial))}</code></div>
    <div>${escapeHtml(getLang() === "zh" ? "材料" : "Material")}: <code>${escapeHtml(materialName || "—")}</code></div>
    <div>${escapeHtml(getLang() === "zh" ? "推荐方向" : "Recommended directions")}: <code>${escapeHtml(topRts.join(", ") || "—")}</code></div>
    ${materialDescription ? `<div class="manual-linked-material-description"><b>${escapeHtml(getLang() === "zh" ? "已载入的材料信息" : "Loaded material information")}:</b> ${escapeHtml(materialDescription)}</div>` : ""}
  `;
}

function renderMaterialDescriptionPreview(materialInput) {
  const material = cleanFeedbackMaterialInput(materialInput);
  const name = String(material.material_name || "").trim();
  if (!name) return getLang() === "zh" ? "填写材料名称后显示组装结果。" : "Enter a material name to preview the assembled description.";
  const listText = (value) => (Array.isArray(value) ? value.join("、") : String(value || ""));
  const sentences = [`材料是${name}。`];
  if (material.major_category) sentences.push(`材料类别是${material.major_category}。`);
  if (material.components) sentences.push(`材料组分包括：${listText(material.components)}。`);
  if (material.structure_relationships) sentences.push(`结构关系：${material.structure_relationships}。`);
  if (material.precursors) sentences.push(`该材料是以${listText(material.precursors)}为前驱体。`);
  if (material.feed_ratio) sentences.push(`前驱体投料比为：${material.feed_ratio}。`);
  if (material.preparation_method) sentences.push(`通过${material.preparation_method}的方式制备。`);
  if (material.elements) sentences.push(`含有元素：${listText(material.elements)}。`);
  if (material.element_content) sentences.push(`元素含量大概分别为：${listText(material.element_content)}。`);
  if (material.conditions) sentences.push(`已有实验或测试条件：${material.conditions}。`);
  if (material.custom_prompt) sentences.push(`实验人员补充信息：${material.custom_prompt}`);
  return sentences.join("");
}

function updateManualGroupMaterialPreview(group) {
  const preview = group?.el?.querySelector(".manual-material-preview");
  const materialInput = readManualGroupMaterialInputFromDom(group);
  group.materialInput = materialInput;
  if (preview) preview.textContent = renderMaterialDescriptionPreview(materialInput);
  renderManualGroupSummary(group);
  updateManualGroupMeta(group);
}

function renderAllManualGroupSummaries() {
  for (const gid of manualGroups) renderManualGroupSummary(manualGroupStates[gid]);
}

async function fetchRecoJobIfNeeded(jobId) {
  const id = String(jobId || "").trim();
  if (!id) return null;
  if (manualRecoJobCache[id]) return manualRecoJobCache[id];
  try {
    const j = await apiJson(`/api/jobs/${encodeURIComponent(id)}`, { method: "GET", headers: {} });
    manualRecoJobCache[id] = j;
    return j;
  } catch {
    return null;
  }
}

async function fetchRecoResultIfNeeded(jobId) {
  const id = String(jobId || "").trim();
  if (!id) return null;
  if (manualRecoResultCache[id]) return manualRecoResultCache[id];
  try {
    const payload = await apiJson(`/api/jobs/${encodeURIComponent(id)}/result`, { method: "GET", headers: {} });
    manualRecoResultCache[id] = payload;
    return payload;
  } catch {
    return null;
  }
}

async function fetchJobLogIfNeeded(jobId) {
  const id = String(jobId || "").trim();
  if (!id) return null;
  if (jobLogCache[id] != null) return jobLogCache[id];
  try {
    const text = await apiText(`/api/jobs/${encodeURIComponent(id)}/log`, { method: "GET", headers: {} });
    jobLogCache[id] = text;
    return text;
  } catch {
    return null;
  }
}

async function loadRecoForManualGroup(groupId, recoJobId, { makeActive = true } = {}) {
  const gid = String(groupId || "").trim();
  const group = manualGroupStates[gid];
  const id = String(recoJobId || "").trim();
  if (!group) return;

  // Save previous draft before switching.
  saveManualGroupDraftNow(gid);

  if (!id) {
    group.recoJobId = null;
    group.recoItem = null;
    group.resultPayload = null;
    group.predByRt = {};
    group.el.querySelectorAll("tbody.manual-group-rows tr").forEach((tr) => syncManualRowByRt(tr, group));
    renderManualGroupSummary(group);
    updateManualGroupMeta(group);
    updateManualGroupMaterialPreview(group);
    if (makeActive) setManualGroupActive(gid);
    persistManualGroupsToStorage();
    return;
  }

  if (isRecoJobIdUsed(id, { exceptGroupId: gid })) {
    alert(getLang() === "zh" ? "该推荐记录已在其它反馈块中使用，请勿重复选择。" : "This recommendation is already used in another block.");
    renderRecoOptionsForGroup(group);
    return;
  }

  group.recoJobId = id;
  group.recoItem = manualRecoList.find((x) => x.job_id === id) || null;
  group.resultPayload = null;
  group.predByRt = {};

  renderManualGroupSummary(group);
  updateManualGroupMeta(group);

  // Ensure we have job meta if it's not in /api/recommendations list.
  let recoJobPayload = manualRecoJobCache[id] || null;
  if (!group.recoItem) {
    const j = await fetchRecoJobIfNeeded(id);
    recoJobPayload = j || recoJobPayload;
    if (j && j.job_type === "mad_rank" && j.status === "completed" && !j.deleted_at_utc) {
      group.recoItem = {
        job_id: j.id,
        created_at_utc: j.created_at_utc,
        finished_at_utc: j.finished_at_utc,
        material_name: j.payload?.material_name || "",
        material_input: j.payload?.material_input || null,
        components: j.payload?.components || "",
        detected_count: j.payload?.detected_count || null,
        top_k_reactions: j.payload?.top_k_reactions || 2,
        reaction_types: j.payload?.reaction_types || null,
        result_url: `/api/jobs/${encodeURIComponent(j.id)}/result`,
      };
    }
  } else {
    recoJobPayload = (await fetchRecoJobIfNeeded(id)) || recoJobPayload;
  }

  const draftBundle = loadManualDraftBundle(id);
  const recommendationDefaults = recommendationMaterialInputDefaults(group.recoItem, recoJobPayload);
  const draftMaterialInput = draftBundle.material_input || {};
  const materialInput = draftBundle.schema_version >= MANUAL_DRAFT_SCHEMA_VERSION
    ? cleanFeedbackMaterialInput({
        ...draftMaterialInput,
        ...(draftMaterialInput.material_serial_no == null && recommendationDefaults.material_serial_no != null
          ? { material_serial_no: recommendationDefaults.material_serial_no }
          : {}),
      })
    : cleanFeedbackMaterialInput({ ...recommendationDefaults, ...draftMaterialInput });
  writeManualGroupMaterialInputToDom(group, materialInput);
  const structuredDetails = group.el.querySelector("details.feedback-structured-details");
  if (structuredDetails && hasStructuredMaterialFields(materialInput)) structuredDetails.open = true;

  const payload = await fetchRecoResultIfNeeded(id);
  if (!payload) {
    group.resultPayload = null;
    group.predByRt = {};
  } else {
    group.resultPayload = payload;
    group.predByRt = predMapFromRankResult(payload);
  }

  // Load draft rows for this recommendation.
  clearManualGroupRows(group);
  group.suspendSave = true;
  try {
    const draft = draftBundle.rows || [];
    if (draft && draft.length) {
      for (const r of draft) addManualRowToGroup(group, r);
    } else {
      const topRts = pickTopReactionTypes(payload || {}, group.recoItem?.top_k_reactions || 2);
      if (!topRts.length) {
        addManualRowToGroup(group, { reaction_type: DEFAULT_PROPERTY_TYPE });
      } else {
        for (const rt of topRts) addManualRowToGroup(group, { reaction_type: rt });
      }
    }
  } finally {
    group.suspendSave = false;
  }

  // Persist.
  if (makeActive) setManualGroupActive(gid);
  persistManualGroupsToStorage();
  saveManualGroupDraftNow(gid);
  renderManualGroupSummary(group);
  updateManualGroupMaterialPreview(group);
}

function createManualGroupCard() {
  const container = manualGroupsContainer();
  if (!container) return null;

  const groupId = `g${++manualGroupCounter}`;
  const defaultSerial = manualGroups.length + 1;
  const el = document.createElement("div");
  el.className = "card small manual-group";
  el.setAttribute("data-group-id", groupId);
  el.innerHTML = `
    <div class="row">
      <label class="inline">
        <input type="checkbox" class="manual-group-submit" />
        <span class="muted" data-i18n="manual_group_submit_label"></span>
      </label>
      <label class="grow">
        <span class="muted" data-i18n="manual_group_reco_label"></span>
        <select class="select manual-group-reco"></select>
      </label>
      <button type="button" class="secondary manual-group-remove" data-i18n="btn_remove_group"></button>
    </div>
    <div class="hint muted manual-group-summary"></div>
    <div class="feedback-material-fields stack">
      <label>
        <span data-i18n="material_serial_no_label"></span>
        <input class="feedback-material-serial-no" type="number" min="1" step="1" inputmode="numeric" data-i18n-placeholder="material_serial_no_label" value="${defaultSerial}" />
        <div class="hint muted" data-i18n="material_serial_no_hint"></div>
      </label>
      <label>
        <span data-i18n="material_name_label"></span>
        <input class="feedback-material-name" type="text" data-i18n-placeholder="material_name_placeholder" />
        <div class="hint muted" data-i18n="material_name_hint"></div>
      </label>
      <label>
        <span data-i18n="custom_prompt_label"></span>
        <textarea class="feedback-custom-prompt" rows="3" data-i18n-placeholder="custom_prompt_placeholder"></textarea>
        <div class="hint muted" data-i18n="custom_prompt_hint"></div>
      </label>
      <details class="details feedback-structured-details">
        <summary data-i18n="structured_material_fields"></summary>
        <div class="feedback-structured-grid">
          <label><span data-i18n="major_category_label"></span><input class="feedback-major-category" type="text" /></label>
          <label><span data-i18n="material_components_label"></span><input class="feedback-components" type="text" /></label>
          <label class="span-2"><span data-i18n="structure_relationships_label"></span><input class="feedback-structure-relationships" type="text" /></label>
          <label><span data-i18n="precursors_label"></span><input class="feedback-precursors" type="text" /></label>
          <label><span data-i18n="feed_ratio_label"></span><input class="feedback-feed-ratio" type="text" /></label>
          <label class="span-2"><span data-i18n="preparation_method_label"></span><input class="feedback-preparation-method" type="text" /></label>
          <label><span data-i18n="elements_label"></span><input class="feedback-elements" type="text" /></label>
          <label><span data-i18n="element_content_label"></span><input class="feedback-element-content" type="text" /></label>
          <label class="span-2"><span data-i18n="conditions_label"></span><input class="feedback-conditions" type="text" /></label>
        </div>
      </details>
      <details class="details feedback-preview-details">
        <summary data-i18n="feedback_prompt_preview"></summary>
        <div class="manual-material-preview md-block muted"></div>
      </details>
    </div>
    <div class="table-wrap">
      <table class="table manual-feedback-table">
        <colgroup>
          <col class="col-rt" />
          <col class="col-pred" />
          <col class="col-value" />
          <col class="col-condition" />
          <col class="col-notes" />
          <col class="col-actions" />
        </colgroup>
        <thead>
          <tr>
            <th data-i18n="col_reaction"></th>
            <th data-i18n="col_predicted"></th>
            <th data-i18n="col_value"></th>
            <th data-i18n="col_condition"></th>
            <th data-i18n="col_product"></th>
            <th></th>
          </tr>
        </thead>
        <tbody class="manual-group-rows"></tbody>
      </table>
    </div>
    <div class="row">
      <button type="button" class="secondary manual-group-add-row" data-i18n="btn_add_row"></button>
      <button type="button" class="secondary manual-group-clear-draft" data-i18n="btn_clear_draft"></button>
    </div>
    <div class="hint muted manual-group-meta"></div>
  `;
  container.appendChild(el);
  applyI18n();

  const group = {
    groupId,
    el,
    recoJobId: null,
    recoItem: null,
    resultPayload: null,
    predByRt: {},
    materialInput: {},
    saveTimer: null,
    suspendSave: false,
  };
  manualGroupStates[groupId] = group;
  manualGroups.push(groupId);

  // UX: keep "active group" in sync with where the user is editing.
  // Use focusin/click (not mousedown) to avoid interfering with native <select> opening behavior.
  el.addEventListener("focusin", () => setManualGroupActive(groupId));
  el.addEventListener("click", (ev) => {
    if (!isInteractiveDomTarget(ev.target)) setManualGroupActive(groupId);
  });

  el.querySelector("select.manual-group-reco")?.addEventListener("change", async (e) => {
    setManualGroupActive(groupId);
    await loadRecoForManualGroup(groupId, e.target.value || "");
  });
  el.querySelectorAll(".feedback-material-fields input, .feedback-material-fields textarea").forEach((input) => {
    const onMaterialChange = () => {
      setManualGroupActive(groupId);
      updateManualGroupMaterialPreview(group);
      scheduleSaveManualGroupDraft(groupId);
    };
    input.addEventListener("input", onMaterialChange);
    input.addEventListener("change", onMaterialChange);
  });
  el.querySelector("button.manual-group-add-row")?.addEventListener("click", () => {
    setManualGroupActive(groupId);
    addManualRowToGroup(group);
    scheduleSaveManualGroupDraft(groupId);
  });
  el.querySelector("button.manual-group-clear-draft")?.addEventListener("click", () => {
    setManualGroupActive(groupId);
    const ok = confirm(getLang() === "zh" ? "确定要清空该材料反馈块吗？" : "Clear this material feedback block?");
    if (!ok) return;
    if (group.recoJobId) clearManualDraft(group.recoJobId);
    const recoJob = group.recoJobId ? manualRecoJobCache[group.recoJobId] || null : null;
    const materialInput = group.recoJobId ? recommendationMaterialInputDefaults(group.recoItem, recoJob) : {};
    writeManualGroupMaterialInputToDom(group, materialInput);
    const payload = group.resultPayload || {};
    const topRts = pickTopReactionTypes(payload, group.recoItem?.top_k_reactions || 2);
    group.suspendSave = true;
    try {
      clearManualGroupRows(group);
      if (!topRts.length) {
        addManualRowToGroup(group, { reaction_type: DEFAULT_PROPERTY_TYPE });
      } else {
        for (const rt of topRts) addManualRowToGroup(group, { reaction_type: rt });
      }
    } finally {
      group.suspendSave = false;
    }
    saveManualGroupDraftNow(groupId);
    updateManualGroupMaterialPreview(group);
  });
  el.querySelector("button.manual-group-remove")?.addEventListener("click", () => {
    setManualGroupActive(groupId);
    removeManualGroup(groupId);
  });

  // Start with one empty row so the table structure is visible.
  addManualRowToGroup(group, { reaction_type: DEFAULT_PROPERTY_TYPE });
  updateManualGroupMeta(group);
  renderRecoOptionsForGroup(group);
  setManualGroupActive(groupId);
  updateManualGroupMaterialPreview(group);

  return group;
}

function removeManualGroup(groupId) {
  const gid = String(groupId || "").trim();
  const group = manualGroupStates[gid];
  if (!group) return;

  // Cancel timers.
  if (group.saveTimer) clearTimeout(group.saveTimer);

  // Remove DOM and state.
  group.el?.remove();
  delete manualGroupStates[gid];
  manualGroups = manualGroups.filter((x) => x !== gid);

  // Pick a new active group if needed.
  if (manualActiveGroupId === gid) {
    manualActiveGroupId = null;
    const next = getActiveManualGroup();
    if (next) setManualGroupActive(next.groupId);
  }

  // Ensure at least one group exists.
  if (!manualGroups.length) createManualGroupCard();

  persistManualGroupsToStorage();
}

function ensureManualGroupsInitialized() {
  const container = manualGroupsContainer();
  if (!container) return;

  // If already initialized, no-op.
  if (manualGroups.length) {
    renderRecoOptionsForAllManualGroups();
    return;
  }

  const stored = getManualOpenRecoJobIds();
  if (!stored.length) {
    createManualGroupCard();
    return;
  }

  for (const jobId of stored) {
    const g = createManualGroupCard();
    if (!g) continue;
    const sel = g.el.querySelector("select.manual-group-reco");
    if (sel) sel.value = jobId;
    // Fire async load (best-effort).
    // Important: don't auto-switch "active" during restore; otherwise whichever load
    // finishes last can override the user's previously active block.
    loadRecoForManualGroup(g.groupId, jobId, { makeActive: false }).catch(() => {});
  }

  // Restore active reco if possible.
  const activeReco = getManualActiveRecoJobId();
  if (activeReco) {
    for (const gid of manualGroups) {
      if (manualGroupStates[gid]?.recoJobId === activeReco) {
        setManualGroupActive(gid);
        break;
      }
    }
  }
}

function buildManualCsvForGroup(group, { includeHeader = true } = {}) {
  const serialRaw = String(group?.el?.querySelector(FEEDBACK_MATERIAL_SELECTORS.material_serial_no)?.value || "").trim();
  if (serialRaw && normalizeMaterialSerial(serialRaw) == null) {
    throw new Error(getLang() === "zh" ? "材料序号必须是大于等于 1 的正整数。" : "Material serial number must be a positive integer.");
  }
  const materialInput = readManualGroupMaterialInputFromDom(group);
  const materialName = String(materialInput.material_name || "").trim();
  if (!materialName) {
    throw new Error(getLang() === "zh" ? "材料名称是必填项。" : "Material name is required.");
  }
  materialInput.material_name = materialName;
  const recoJobId = String(group?.recoJobId || "").trim();
  const rows = Array.from(group?.el?.querySelectorAll("tbody.manual-group-rows tr") || []);
  const out = [];
  if (includeHeader)
    out.push(
      [
        "recommendation_job_id",
        "material_serial_no",
        "material_name",
        "material_input_json",
        "elements",
        "task_type",
        "value",
        "unit",
        "product",
        "faradaic_efficiency",
        "faradaic_efficiency_unit",
        "partial_current_density",
        "partial_current_density_unit",
        "condition",
        "notes",
      ].join(",")
    );
  const explicitElements = Array.isArray(materialInput.elements)
    ? materialInput.elements.map((item) => String(item || "").trim()).filter(Boolean).join(", ")
    : String(materialInput.elements || "").trim();
  const materialInputJson = JSON.stringify(materialInput);
  for (const tr of rows) {
    const row = readManualRowFromDom(tr);
    const rt = canonicalRt(row.task_type || row.property_type || row.reaction_type) || "";
    const value = String(row.value || "").trim();
    const unit = String(row.unit || "").trim();
    const product = String(row.product || "").trim();
    const faradaicEfficiency = String(row.faradaic_efficiency || "").trim();
    const partialCurrent = String(row.partial_current_density || "").trim();
    const partialUnit = String(row.partial_current_density_unit || "mA cm-2").trim();
    const condition = String(row.condition || "").trim();
    const notes = String(row.notes || "").trim();
    if (!rt) continue;
    if (!manualRowIsComplete(row)) continue;
    const rules = RT_RULES[rt] || RT_RULES[DEFAULT_PROPERTY_TYPE];
    if (rules.requireCondition && !condition) {
      throw new Error(getLang() === "zh" ? `${rt} 需要条件：10 mA cm-2。` : `${rt} requires condition=10 mA cm-2.`);
    }
    out.push(
      [
        recoJobId,
        materialInput.material_serial_no == null ? "" : materialInput.material_serial_no,
        materialName,
        materialInputJson,
        explicitElements,
        rt,
        rt === "CO2RR" ? "" : value,
        rt === "CO2RR" ? "" : unit,
        rt === "CO2RR" ? product : "",
        rt === "CO2RR" ? faradaicEfficiency : "",
        rt === "CO2RR" ? "%" : "",
        rt === "CO2RR" ? partialCurrent : "",
        rt === "CO2RR" ? partialUnit : "",
        condition,
        notes,
      ]
        .map(csvEscape)
        .join(",")
    );
  }
  return out.join("\n") + "\n";
}

async function refreshRecoList() {
  const q = document.getElementById("reco-search")?.value?.trim() || "";
  const url = `/api/recommendations?limit=80${q ? `&q=${encodeURIComponent(q)}` : ""}`;
  const data = await apiJson(url, { method: "GET", headers: {} });
  manualRecoList = Array.isArray(data.items) ? data.items : [];
  ensureManualGroupsInitialized();
  renderRecoOptionsForAllManualGroups();
}

function recoSuggestionsBox() {
  return document.getElementById("reco-suggestions");
}

function hideRecoSuggestions() {
  const box = recoSuggestionsBox();
  if (!box) return;
  box.classList.add("hidden");
  box.innerHTML = "";
}

function renderRecoSuggestionButtons(items) {
  const it = Array.isArray(items) ? items : [];
  if (!it.length) return `<div class="muted">${escapeHtml(getLang() === "zh" ? "（无匹配项）" : "(no matches)")}</div>`;

  return it
    .map((x) => {
      const jobId = String(x?.job_id || "").trim();
      const materialName = recommendationMaterialDisplayName(x).replaceAll("\n", " ").trim();
      const serial = materialSerialFromValue(x);
      const whenUtc = x?.finished_at_utc || x?.created_at_utc || "";
      const when = whenUtc ? fmtBeijing(String(whenUtc)) : "—";
      return `
        <button type="button" class="suggestion-item" data-job="${escapeHtml(jobId)}">
          <span class="suggestion-id">${escapeHtml(serial == null ? shortId(jobId, 10) : `#${serial}`)}</span>
          <span class="suggestion-comp">${escapeHtml(materialName || "—")}</span>
          <span class="suggestion-time">${escapeHtml(when)}</span>
        </button>
      `;
    })
    .join("");
}

async function addRecoJobToManualGroups(recoJobId, { makeActive = true } = {}) {
  const jobId = String(recoJobId || "").trim();
  if (!jobId) return null;

  ensureManualGroupsInitialized();

  // Reuse an existing block if present.
  for (const gid of manualGroups) {
    const st = manualGroupStates[gid];
    if (st?.recoJobId === jobId) {
      if (makeActive) setManualGroupActive(gid);
      st.el?.scrollIntoView?.({ behavior: "smooth", block: "start" });
      return st;
    }
  }

  const group = createManualGroupCard();
  if (!group) throw new Error(getLang() === "zh" ? "无法创建反馈块（manual-groups 容器不存在）" : "Failed to create a manual feedback block.");
  const sel = group.el.querySelector("select.manual-group-reco");
  if (sel) sel.value = jobId;
  await loadRecoForManualGroup(group.groupId, jobId, { makeActive });
  if (makeActive) setManualGroupActive(group.groupId);
  group.el?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  return group;
}

async function refreshRecoSuggestions(query) {
  const q = String(query || "").trim();
  const box = recoSuggestionsBox();
  if (!box) return;

  if (!q) {
    hideRecoSuggestions();
    return;
  }

  const seq = ++recoSuggestSeq;
  box.classList.remove("hidden");
  box.innerHTML = `<div class="muted">${escapeHtml(t("loading"))}</div>`;

  try {
    const url = `/api/recommendations?limit=20&q=${encodeURIComponent(q)}`;
    const data = await apiJson(url, { method: "GET", headers: {} });
    if (seq !== recoSuggestSeq) return;
    const items = Array.isArray(data.items) ? data.items : [];
    box.innerHTML = renderRecoSuggestionButtons(items);
    box.querySelectorAll("button.suggestion-item").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const jobId = btn.getAttribute("data-job") || "";
        if (!jobId) return;
        try {
          await addRecoJobToManualGroups(jobId, { makeActive: true });
        } catch (e) {
          alert(String(e.message || e));
        } finally {
          hideRecoSuggestions();
        }
      });
    });
  } catch (e) {
    box.innerHTML = `${pill("failed")} ${escapeHtml(String(e.message || e))}`;
  }
}

function scheduleRecoSuggestionsRefresh() {
  const input = document.getElementById("reco-search");
  if (!input) return;
  if (recoSuggestTimer) clearTimeout(recoSuggestTimer);
  recoSuggestTimer = setTimeout(() => {
    refreshRecoSuggestions(input.value).catch(() => {});
  }, 160);
}

function materialSearchTextFromJob(job) {
  const payload = job && typeof job === "object" ? job.payload || {} : {};
  const materialInput = materialInputFromJob(job);
  const taskTypes = [payload.task_types, payload.property_types, payload.reaction_types]
    .flatMap((value) => (Array.isArray(value) ? value : []))
    .map((value) => String(value || ""));
  return [
    materialInput.material_serial_no == null ? "" : String(materialInput.material_serial_no),
    materialInput.material_name || "",
    JSON.stringify(materialInput),
    taskTypes.join(" "),
    String(job?.id || ""),
    String(job?.status || ""),
  ]
    .join(" ")
    .toLowerCase();
}

function renderHistoryRecoTable(jobs) {
  const items = Array.isArray(jobs) ? jobs : [];
  if (!items.length) return `<div class="muted">${escapeHtml(t("empty"))}</div>`;

  const headTime = escapeHtml(getLang() === "zh" ? "时间（北京时间）" : "Time (CST)");
  const headStatus = escapeHtml(getLang() === "zh" ? "状态" : "Status");
  const headSerial = escapeHtml(getLang() === "zh" ? "序号" : "Serial");
  const headComp = escapeHtml(getLang() === "zh" ? "材料" : "Material");
  const headId = escapeHtml(getLang() === "zh" ? "任务ID" : "Job");
  const headAct = escapeHtml(getLang() === "zh" ? "操作" : "Actions");

  const rows = items
    .map((j) => {
      const started = j.started_at_utc ? fmtBeijing(j.started_at_utc) : "—";
      const finished = j.finished_at_utc ? fmtBeijing(j.finished_at_utc) : "—";
      const duration = fmtDurationSeconds(durationSecondsForJob(j));
      const materialInput = materialInputFromJob(j);
      const materialName = String(materialInput.material_name || "").replaceAll("\n", " ").trim();
      const serial = materialSerialFromValue(materialInput);
      const description = materialName ? renderMaterialDescriptionPreview(materialInput) : legacyMaterialRecordLabel();
      const shortDescription = description.length > 180 ? description.slice(0, 180) + "…" : description;
      const jobId = String(j.id || "");
      const deletedAt = j.deleted_at_utc ? fmtBeijing(j.deleted_at_utc) : null;

      const canUse = j.status === "completed" && !j.deleted_at_utc;
      const canViewResult = j.status === "completed";
      const useBtn = `
        <button type="button" class="secondary btn-use-feedback" data-job="${escapeHtml(jobId)}" ${canUse ? "" : "disabled"}>
          ${escapeHtml(t("btn_use_for_feedback"))}
        </button>
      `;
      const viewResultBtn = `
        <button type="button" class="secondary btn-toggle-reco-result" data-job="${escapeHtml(jobId)}" ${canViewResult ? "" : "disabled"}>
          ${escapeHtml(t("btn_view_result"))}
        </button>
      `;
      const viewLogBtn = `
        <button type="button" class="secondary btn-toggle-reco-log" data-job="${escapeHtml(jobId)}">
          ${escapeHtml(t("btn_view_log"))}
        </button>
      `;
      const hideRestoreBtn = j.deleted_at_utc
        ? `<button type="button" class="secondary btn-restore-job" data-job="${escapeHtml(jobId)}">${escapeHtml(t("btn_restore_job"))}</button>`
        : `<button type="button" class="secondary btn-hide-job" data-job="${escapeHtml(jobId)}">${escapeHtml(t("btn_hide_job"))}</button>`;

      const deletedNote = deletedAt
        ? `<div class="muted">${escapeHtml(getLang() === "zh" ? "已隐藏于" : "Hidden at")}: <code>${escapeHtml(deletedAt)}</code></div>`
        : "";

      return `
        <tr class="history-reco-row" data-job="${escapeHtml(jobId)}">
          <td>
            <div>${escapeHtml(t("started_at"))}: <code>${escapeHtml(started)}</code></div>
            <div>${escapeHtml(t("finished_at"))}: <code>${escapeHtml(finished)}</code></div>
            <div>${escapeHtml(t("duration"))}: <code>${escapeHtml(duration)}</code></div>
          </td>
          <td>${pill(j.status || "")}</td>
          <td><code>${escapeHtml(serial == null ? "—" : String(serial))}</code></td>
          <td>
            <div><b>${serial == null ? "" : `#${escapeHtml(String(serial))} `}${escapeHtml(materialName || legacyMaterialRecordLabel())}</b></div>
            <div class="muted history-material-description">${escapeHtml(shortDescription)}</div>
            ${deletedNote}
          </td>
          <td><code>${escapeHtml(jobId)}</code></td>
          <td class="row">
            ${useBtn}
            ${viewResultBtn}
            ${viewLogBtn}
            ${hideRestoreBtn}
          </td>
        </tr>
        <tr class="history-reco-result-row hidden" data-job="${escapeHtml(jobId)}">
          <td colspan="6">
            <div class="card small history-reco-result muted">${escapeHtml(getLang() === "zh" ? "点击“查看结果”加载结果…" : "Click “View result” to load result…")}</div>
          </td>
        </tr>
        <tr class="history-reco-log-row hidden" data-job="${escapeHtml(jobId)}">
          <td colspan="6">
            <div class="card small history-reco-log muted">${escapeHtml(getLang() === "zh" ? "点击“查看日志”加载日志…" : "Click “View log” to load logs…")}</div>
          </td>
        </tr>
      `;
    })
    .join("");

  return `
    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>${headTime}</th>
            <th>${headStatus}</th>
            <th>${headSerial}</th>
            <th>${headComp}</th>
            <th>${headId}</th>
            <th>${headAct}</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function renderHistoryRecoResultBox(jobId, payload, jobMeta = null) {
  const top = Array.isArray(payload?.top_k) ? payload.top_k : [];
  const ranking = Array.isArray(payload?.ranking) ? payload.ranking : [];

  const resultMaterialInput = cleanFeedbackMaterialInput({
    ...materialInputFromJob(jobMeta),
    ...(payload?.material_input && typeof payload.material_input === "object" ? payload.material_input : {}),
    ...(payload?.material_name ? { material_name: payload.material_name } : {}),
  });
  const materialName = String(resultMaterialInput.material_name || "").trim();
  const serial = materialSerialFromValue(resultMaterialInput);
  const materialDescription = materialName ? renderMaterialDescriptionPreview(resultMaterialInput) : "";
  const timing = payload?.recommendation_timing && typeof payload.recommendation_timing === "object" ? payload.recommendation_timing : {};
  const timingJob = {
    started_at_utc: timing.started_at_utc || jobMeta?.started_at_utc || null,
    finished_at_utc: timing.finished_at_utc || jobMeta?.finished_at_utc || null,
    duration_seconds: timing.duration_seconds ?? jobMeta?.duration_seconds ?? null,
  };
  const started = timingJob.started_at_utc ? fmtBeijing(timingJob.started_at_utc) : "—";
  const finished = timingJob.finished_at_utc ? fmtBeijing(timingJob.finished_at_utc) : "—";
  const duration = fmtDurationSeconds(durationSecondsForJob(timingJob));

  const topHtml = top.length
    ? `
      <div class="stack">
        ${top
          .map((it, idx) => {
            const rt = canonicalRt(it?.task_type || it?.reaction_type || it?.property_type) || String(it?.task_type || it?.reaction_type || it?.property_type || "").trim();
            const evidence = String(it?.final_performance || "").includes("rag:chroma") ? t("evidence_rag") : t("evidence_llm");
            const consensus = it?.consensus_reached ? t("consensus_yes") : t("consensus_no");
            const metricLine = predLineFromRankItem(it);
            const grade = String(it?.performance_evaluation?.grade || it?.grade || "").trim();
            const normalizedScore = Number(it?.normalized_score);
            const scoreText = Number.isFinite(normalizedScore) ? normalizedScore.toFixed(2) : "—";
            const debateSummary = getLang() === "zh" ? "查看辩论过程与轨迹（保存的运行轨迹）" : "View debate trace (saved run trajectory)";
            const debateHint =
              getLang() === "zh"
                ? "提示：若提示“找不到轨迹”，说明这次推荐没有开启保存辩论轨迹（需要 --save-each-reaction）。"
                : "Tip: if it says “trace not found”, this recommendation was not run with --save-each-reaction.";
            return `
              <div class="card small">
                <div class="row">
                  <b>#${idx + 1} ${escapeHtml(rt || "—")}</b>
                  <span class="muted">${escapeHtml(consensus)}</span>
                </div>
                <div class="stack">
                  <div>
                    ${escapeHtml(getLang() === "zh" ? "关键指标" : "Key metric")}: <code>${escapeHtml(metricLine)}</code>
                    ${grade ? ` · ${escapeHtml(getLang() === "zh" ? "等级" : "Grade")}: <code>${escapeHtml(grade)}</code>` : ""}
                    · ${escapeHtml(getLang() === "zh" ? "标准化分数" : "Normalized score")}: <code>${escapeHtml(scoreText)}</code>
                    · ${escapeHtml(evidence)}
                  </div>
                  <details class="details">
                    <summary>${escapeHtml(getLang() === "zh" ? "最终结论文本（final_performance）" : "Final conclusion text (final_performance)")}</summary>
                    <pre class="log">${escapeHtml(String(it?.final_performance || "").trim() || "—")}</pre>
                  </details>
                  <details class="details history-debate-details" data-job="${escapeHtml(jobId)}" data-rt="${escapeHtml(rt)}">
                    <summary>${escapeHtml(debateSummary)}</summary>
                    <div class="hint muted">${escapeHtml(debateHint)}</div>
                    <div class="card small muted history-debate-box" data-loaded="0">
                      ${escapeHtml(getLang() === "zh" ? "打开后会自动加载。内容可能较长，请稍等…" : "Open to load automatically. Content may be long…")}
                    </div>
                  </details>
                </div>
              </div>
            `;
          })
          .join("")}
      </div>
    `
    : `<div class="muted">${escapeHtml(getLang() === "zh" ? "（无 top_k 结果）" : "(no top_k results)")}</div>`;

  const rankRows = ranking
    .map((it, idx) => {
      const rt = canonicalRt(it?.task_type || it?.reaction_type || it?.property_type) || String(it?.task_type || it?.reaction_type || it?.property_type || "").trim();
      const metric = it?.performance_evaluation || {};
      const metricName = String(metric.metric_name || "").trim();
      const metricVal = predLineFromRankItem(it);
      const grade = String(metric.grade || it?.grade || "").trim();
      const normalizedScore = Number(it?.normalized_score);
      const scoreText = Number.isFinite(normalizedScore) ? normalizedScore.toFixed(2) : "—";
      return `
        <tr>
          <td class="muted"><code>${escapeHtml(String(idx + 1))}</code></td>
          <td><code>${escapeHtml(rt || "—")}</code></td>
          <td class="muted"><code>${escapeHtml(metricName || "—")}</code></td>
          <td><code>${escapeHtml(String(metricVal || "—"))}</code></td>
          <td><code>${escapeHtml(grade || "—")}</code></td>
          <td><code>${escapeHtml(scoreText)}</code></td>
        </tr>
      `;
    })
    .join("");

  const fullRanking =
    ranking.length > 0
      ? `
        <details class="details">
          <summary>${escapeHtml(getLang() === "zh" ? "完整排序（全部方向）" : "Full ranking (all directions)")}</summary>
          <div class="table-wrap">
            <table class="table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>${escapeHtml(getLang() === "zh" ? "任务方向" : "Direction")}</th>
                  <th>${escapeHtml(getLang() === "zh" ? "指标" : "Metric")}</th>
                  <th>${escapeHtml(getLang() === "zh" ? "预测值" : "Pred")}</th>
                  <th>${escapeHtml(getLang() === "zh" ? "等级" : "Grade")}</th>
                  <th>${escapeHtml(getLang() === "zh" ? "标准化分数" : "Normalized score")}</th>
                </tr>
              </thead>
              <tbody>${rankRows}</tbody>
            </table>
          </div>
        </details>
      `
      : "";

  return `
    <div class="row">
      <span class="pill ok">${escapeHtml(getLang() === "zh" ? "结果已加载" : "Result loaded")}</span>
      <a class="secondary" href="/api/jobs/${encodeURIComponent(jobId)}/result" target="_blank" rel="noreferrer">${escapeHtml(t("download_json"))}</a>
    </div>
    <div class="stack">
      <div>${escapeHtml(getLang() === "zh" ? "材料序号" : "Material serial")}: <code>${escapeHtml(serial == null ? "—" : String(serial))}</code></div>
      <div>${escapeHtml(getLang() === "zh" ? "材料名称" : "Material name")}: <code>${escapeHtml(materialName || legacyMaterialRecordLabel())}</code></div>
      ${materialDescription ? `<div class="muted history-material-description">${escapeHtml(materialDescription)}</div>` : ""}
      <div class="muted">
        ${escapeHtml(t("started_at"))}: <code>${escapeHtml(started)}</code> ·
        ${escapeHtml(t("finished_at"))}: <code>${escapeHtml(finished)}</code> ·
        ${escapeHtml(t("duration"))}: <code>${escapeHtml(duration)}</code>
      </div>
      <div class="muted">
        ${escapeHtml(getLang() === "zh" ? "运行模式" : "Mode")}: <code>${escapeHtml(String(payload?.selection_mode || "—"))}</code> ·
        ${escapeHtml(getLang() === "zh" ? "独立辩论方向数" : "Independent task debates")}: <code>${escapeHtml(String(payload?.direction_count ?? ranking.length))}</code> ·
        ${escapeHtml(getLang() === "zh" ? "每场范围" : "Debate scope")}: <code>${escapeHtml(String(payload?.debate_scope || "single_task_per_debate"))}</code>
      </div>
      <div><b>${escapeHtml(getLang() === "zh" ? "Top 推荐" : "Top recommendations")}</b></div>
      ${topHtml}
      ${fullRanking}
    </div>
  `;
}

function truncateText(s, maxLen) {
  const text = String(s ?? "");
  const n = Math.max(0, Number(maxLen || 0));
  if (!n || text.length <= n) return text;
  return text.slice(0, n) + "…";
}

function compactDebateEvent(ev) {
  const e = ev && typeof ev === "object" ? ev : {};
  const t0 = String(e.type || "").trim() || "event";
  if (t0 === "propose") {
    return {
      type: "propose",
      proposal_id: e.proposal_id,
      agent_name: e.agent_name,
      claim: truncateText(e.claim, 240),
      total_steps: e.trajectory?.total_steps,
    };
  }
  if (t0 === "review") {
    return {
      type: "review",
      round_number: e.round_number ?? e.round,
      from_proposal_id: e.from_proposal_id,
      target_proposal_id: e.target_proposal_id,
      flaw_type: e.flaw_type,
      valid: e.valid,
      critique: truncateText(e.critique, 280),
    };
  }
  if (t0 === "rebuttal") {
    return {
      type: "rebuttal",
      round_number: e.round_number ?? e.round,
      from_proposal_id: e.from_proposal_id,
      target_proposal_id: e.target_proposal_id,
      rebuttal: truncateText(e.rebuttal, 280),
    };
  }
  if (t0 === "proposal_state") {
    return { type: "proposal_state", proposal_id: e.proposal_id, status: e.status };
  }
  if (t0 === "stalemate_resolution") {
    return { type: "stalemate_resolution", resolution_method: e.resolution_method, details: truncateText(e.details, 320) };
  }
  return { type: t0 };
}

function renderMadDebateTraceBox(jobId, reactionType, payload) {
  const root = payload && typeof payload === "object" ? payload : {};
  const res = root.result && typeof root.result === "object" ? root.result : {};
  const perf = res.performance_evaluation && typeof res.performance_evaluation === "object" ? res.performance_evaluation : {};

  const rt = canonicalRt(perf.reaction_type || reactionType || "");
  const consensus = res.consensus_reached ? t("consensus_yes") : t("consensus_no");
  const rounds = res.debate_rounds != null ? String(res.debate_rounds) : "—";
  const method = String(res.resolution_method || "").trim() || "—";
  const winner = String(res.winner_proposal_id || "").trim() || "—";
  const survive = Array.isArray(res.surviving_proposals) ? res.surviving_proposals.map((x) => String(x || "").trim()).filter(Boolean) : [];
  const defeated = Array.isArray(res.defeated_proposals) ? res.defeated_proposals.map((x) => String(x || "").trim()).filter(Boolean) : [];
  const withdrawn = Array.isArray(res.withdrawn_proposals) ? res.withdrawn_proposals.map((x) => String(x || "").trim()).filter(Boolean) : [];

  const hist = Array.isArray(res.debate_history) ? res.debate_history : [];
  const counts = {};
  for (const ev of hist) {
    const k = String(ev?.type || "").trim() || "event";
    counts[k] = (counts[k] || 0) + 1;
  }
  const countsLine = Object.keys(counts)
    .sort()
    .map((k) => `${k}:${counts[k]}`)
    .join(" · ");

  const proposals = hist.filter((x) => x && x.type === "propose");
  const winnerProp = proposals.find((x) => String(x?.proposal_id || "") === String(res.winner_proposal_id || "")) || null;
  const winnerAgent = String(winnerProp?.agent_name || "").trim() || "—";
  const winnerClaim = String(winnerProp?.claim || "").trim();
  const winnerTraj = winnerProp && typeof winnerProp.trajectory === "object" ? winnerProp.trajectory : null;
  const winnerFinal = winnerTraj ? parseJsonMaybe(winnerTraj.final_answer) : null;
  const winnerConfidence = String(winnerFinal?.confidence || "").trim() || "—";
  const winnerPerf = String(winnerFinal?.performance_metrics || "").trim() || "—";
  const winnerEvidence = Array.isArray(winnerFinal?.evidence) ? winnerFinal.evidence : [];

  const evidenceHtml = winnerEvidence.length
    ? `
      <div class="stack">
        ${(winnerEvidence || [])
          .slice(0, 12)
          .map((e) => {
            const src = String(e?.source_id || "").trim() || "—";
            const quote = String(e?.quote || "").trim();
            return `<div>• <code>${escapeHtml(src)}</code>${quote ? ` — ${escapeHtml(truncateText(quote, 220))}` : ""}</div>`;
          })
          .join("")}
        ${
          winnerEvidence.length > 12
            ? `<div class="muted">${escapeHtml(
                getLang() === "zh"
                  ? "（证据条目较多，已截断显示；可下载原始 JSON 查看完整）"
                  : "(many evidence items; truncated; download raw JSON for full)"
              )}</div>`
            : ""
        }
      </div>
    `
    : `<div class="muted">${escapeHtml(getLang() === "zh" ? "（winner 提案未提供 evidence 结构化字段）" : "(winner proposal has no structured evidence field)")}</div>`;

  const reviewsToWinner = hist
    .filter((x) => x && x.type === "review" && String(x.target_proposal_id || "") === String(res.winner_proposal_id || ""))
    .filter((x) => x.valid !== false);

  const reviewHtml = reviewsToWinner.length
    ? `
      <div class="stack">
        ${reviewsToWinner
          .slice(0, 8)
          .map((r) => {
            const flaw = String(r?.flaw_type || "").trim() || "review";
            const ok = r?.valid === false ? "invalid" : "valid";
            const txt = String(r?.critique || "").trim();
            return `<div>• <code>${escapeHtml(flaw)}</code> <span class="muted">(${escapeHtml(ok)})</span> — ${escapeHtml(truncateText(txt, 240) || "—")}</div>`;
          })
          .join("")}
        ${reviewsToWinner.length > 8 ? `<div class="muted">${escapeHtml(getLang() === "zh" ? "（评价较多，已截断显示）" : "(many reviews; truncated)")}</div>` : ""}
      </div>
    `
    : `<div class="muted">${escapeHtml(getLang() === "zh" ? "（未找到针对 winner 的 review）" : "(no reviews found for winner)")}</div>`;

  const reasoning = String(res.reasoning_trajectory || "").trim();
  const finalPerfText = String(res.final_performance || "").trim();

  const histPreviewRaw = (() => {
    if (!hist.length) return [];
    const head = hist.slice(0, 12).map(compactDebateEvent);
    if (hist.length <= 24) return head;
    const tail = hist.slice(-12).map(compactDebateEvent);
    return [...head, { type: "…", skipped_events: hist.length - 24 }, ...tail];
  })();

  const proposalStatusLine = `
    ${escapeHtml(getLang() === "zh" ? "surviving" : "surviving")}: <code>${escapeHtml(survive.join(", ") || "—")}</code> ·
    ${escapeHtml(getLang() === "zh" ? "defeated" : "defeated")}: <code>${escapeHtml(defeated.join(", ") || "—")}</code> ·
    ${escapeHtml(getLang() === "zh" ? "withdrawn" : "withdrawn")}: <code>${escapeHtml(withdrawn.join(", ") || "—")}</code>
  `;

  return `
    <div class="row">
      <span class="pill ok">${escapeHtml(getLang() === "zh" ? "轨迹已加载" : "Trace loaded")}</span>
      <a class="secondary" href="/api/jobs/${encodeURIComponent(jobId)}/mad_traces/${encodeURIComponent(String(rt || reactionType || ""))}" target="_blank" rel="noreferrer">
        ${escapeHtml(getLang() === "zh" ? "下载轨迹 JSON" : "Download trace JSON")}
      </a>
    </div>
    <div class="stack">
      <div>${escapeHtml(getLang() === "zh" ? "任务方向" : "Direction")}: <code>${escapeHtml(rt || "—")}</code> · ${escapeHtml(consensus)}</div>
      <div>${escapeHtml(getLang() === "zh" ? "辩论轮数" : "Debate rounds")}: <code>${escapeHtml(rounds)}</code> · ${escapeHtml(getLang() === "zh" ? "决策方法" : "Resolution")}: <code>${escapeHtml(method)}</code></div>
      <div>${escapeHtml(getLang() === "zh" ? "winner 提案" : "Winner proposal")}: <code>${escapeHtml(winner)}</code> · ${escapeHtml(getLang() === "zh" ? "来自" : "by")}: <code>${escapeHtml(winnerAgent)}</code></div>
      <div class="muted">${escapeHtml(getLang() === "zh" ? "事件统计" : "Event counts")}: <code>${escapeHtml(countsLine || "—")}</code></div>
      <div class="muted">${proposalStatusLine}</div>

      <details class="details" open>
        <summary>${escapeHtml(getLang() === "zh" ? "winner 提案摘要" : "Winner proposal summary")}</summary>
        <div class="stack">
          <div>${escapeHtml(getLang() === "zh" ? "预测" : "Prediction")}: <code>${escapeHtml(winnerPerf)}</code></div>
          <div>${escapeHtml(getLang() === "zh" ? "置信度" : "Confidence")}: <code>${escapeHtml(winnerConfidence)}</code></div>
          ${
            winnerClaim
              ? `<details class="details"><summary>${escapeHtml(getLang() === "zh" ? "提案文本" : "Proposal text")}</summary><pre class="log">${escapeHtml(
                  winnerClaim
                )}</pre></details>`
              : ""
          }
        </div>
      </details>

      <details class="details">
        <summary>${escapeHtml(getLang() === "zh" ? "关键证据（winner.evidence）" : "Key evidence (winner.evidence)")}</summary>
        ${evidenceHtml}
      </details>

      <details class="details">
        <summary>${escapeHtml(getLang() === "zh" ? "针对 winner 的评价（review）" : "Reviews targeting winner")}</summary>
        ${reviewHtml}
      </details>

      ${
        finalPerfText
          ? `<details class="details"><summary>${escapeHtml(
              getLang() === "zh" ? "最终结论（final_performance）" : "Final conclusion (final_performance)"
            )}</summary><pre class="log">${escapeHtml(finalPerfText)}</pre></details>`
          : ""
      }

      ${
        reasoning
          ? `<details class="details"><summary>${escapeHtml(
              getLang() === "zh" ? "完整推理轨迹（reasoning_trajectory）" : "Reasoning trajectory (full)"
            )}</summary><pre class="log">${escapeHtml(reasoning)}</pre></details>`
          : ""
      }

      <details class="details">
        <summary>${escapeHtml(getLang() === "zh" ? "辩论事件预览（debate_history, compact）" : "Debate history preview (compact)")}</summary>
        <pre class="log">${escapeHtml(JSON.stringify(histPreviewRaw, null, 2))}</pre>
      </details>

      <div class="muted">
        ${escapeHtml(
          getLang() === "zh"
            ? "说明：这里只展示“阅读友好”的摘要与预览。更细粒度的工具调用、每步轨迹等，请下载轨迹 JSON 查看。"
            : "Note: this view is a readable summary/preview. For full tool calls and step-level traces, download the trace JSON."
        )}
      </div>
    </div>
  `;
}

function wireHistoryRecoResultBox(containerEl, jobId) {
  const box = containerEl && containerEl.nodeType === 1 ? containerEl : null;
  const jid = String(jobId || "").trim();
  if (!box || !jid) return;

  box.querySelectorAll("details.history-debate-details").forEach((det) => {
    if (det.getAttribute("data-wired") === "1") return;
    det.setAttribute("data-wired", "1");
    det.addEventListener("toggle", async () => {
      if (!det.open) return;
      const rt = String(det.getAttribute("data-rt") || "").trim();
      const detailJobId = String(det.getAttribute("data-job") || jid).trim() || jid;
      const content = det.querySelector(".history-debate-box");
      if (!content) return;
      if (content.getAttribute("data-loaded") === "1") return;
      content.textContent = t("loading");
      try {
        const payload = await apiJson(`/api/jobs/${encodeURIComponent(detailJobId)}/mad_traces/${encodeURIComponent(rt)}`, { method: "GET", headers: {} });
        content.innerHTML = renderMadDebateTraceBox(detailJobId, rt, payload);
        content.classList.remove("muted");
        content.setAttribute("data-loaded", "1");
      } catch (e) {
        const msg = String(e?.message || e);
        const hint =
          getLang() === "zh"
            ? "如果你希望以后都能看到辩论轨迹，请在推荐时开启“保存每个方向的详细辩论记录”。"
            : "To always keep debate traces, run ranking with save-each-reaction enabled.";
        content.innerHTML = `${pill("failed")} ${escapeHtml(msg)}<div class="hint muted">${escapeHtml(hint)}</div>`;
        content.setAttribute("data-loaded", "0");
      }
    });
  });
}

function renderHistoryRecoLogBox(jobId, logText) {
  const text = String(logText || "");
  const lines = text.split(/\r?\n/);
  const keyRe = /(ERROR|Exception|Traceback|WARNING|returncode|killed|oom|timeout|APIConnectionError|Connection error)/i;
  const keyLines = lines.filter((ln) => keyRe.test(ln)).slice(-80);
  const keyBlock = keyLines.length ? keyLines.join("\n") : "";

  const keyTitle = getLang() === "zh" ? "关键行（错误/警告/异常）" : "Key lines (errors/warnings/exceptions)";
  const fullTitle = getLang() === "zh" ? "完整日志（末尾截断）" : "Full log tail (truncated)";

  return `
    <div class="row">
      <span class="pill ok">${escapeHtml(getLang() === "zh" ? "日志已加载" : "Log loaded")}</span>
      <a class="secondary" href="/api/jobs/${encodeURIComponent(jobId)}/log" target="_blank" rel="noreferrer">${escapeHtml(getLang() === "zh" ? "下载日志" : "Download log")}</a>
    </div>
    <div class="stack">
      <details class="details" ${keyBlock ? "open" : ""}>
        <summary>${escapeHtml(keyTitle)}</summary>
        <pre class="log">${escapeHtml(keyBlock || (getLang() === "zh" ? "（未匹配到关键行）" : "(no key lines matched)"))}</pre>
      </details>
      <details class="details">
        <summary>${escapeHtml(fullTitle)}</summary>
        <pre class="log">${escapeHtml(text || (getLang() === "zh" ? "（空）" : "(empty)"))}</pre>
      </details>
    </div>
  `;
}

async function refreshHistoryRecommendations() {
  const list = document.getElementById("history-list");
  const raw = document.getElementById("history-raw");
  if (!list || !raw) return;
  list.textContent = t("loading");
  raw.textContent = t("empty");

  const q = String(document.getElementById("history-search")?.value || "").trim().toLowerCase();
  const qTokens = q.split(/[\s,;，；]+/).filter(Boolean);
  const includeDeleted = Boolean(document.getElementById("history-show-deleted")?.checked);

  try {
    const url = `/api/jobs?limit=200${includeDeleted ? "&include_deleted=1" : ""}`;
    const data = await apiJson(url, { method: "GET", headers: {} });
    const jobs = Array.isArray(data.jobs) ? data.jobs : [];
    const recos = jobs.filter(
      (j) => j && j.job_type === "mad_rank" && Boolean(materialNameFromRecommendation(j))
    );
    const filtered = qTokens.length
      ? recos.filter((j) => {
          const searchable = materialSearchTextFromJob(j);
          return qTokens.every((token) => searchable.includes(token));
        })
      : recos;

    list.innerHTML = renderHistoryRecoTable(filtered);
    raw.textContent = JSON.stringify({ items: filtered }, null, 2);

    list.querySelectorAll(".btn-use-feedback").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const jobId = btn.getAttribute("data-job") || "";
        if (!jobId) return;
        await jumpToManualFeedback(jobId);
      });
    });
    list.querySelectorAll(".btn-toggle-reco-result").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const jobId = btn.getAttribute("data-job") || "";
        if (!jobId) return;

        const row = Array.from(list.querySelectorAll("tr.history-reco-result-row")).find((tr) => tr.getAttribute("data-job") === jobId);
        if (!row) return;

        const box = row.querySelector(".history-reco-result");
        if (!box) return;

        const isOpen = !row.classList.contains("hidden");
        if (isOpen) {
          row.classList.add("hidden");
          btn.textContent = t("btn_view_result");
          return;
        }

        row.classList.remove("hidden");
        btn.textContent = getLang() === "zh" ? "收起" : "Hide";

        if (box.getAttribute("data-loaded") === "1") return;
        box.textContent = t("loading");
        try {
          const payload = await fetchRecoResultIfNeeded(jobId);
          if (!payload) throw new Error(getLang() === "zh" ? "无法读取结果（可能已被清理）。" : "Failed to read result payload.");
          const jobMeta = filtered.find((item) => String(item?.id || "") === jobId) || null;
          box.innerHTML = renderHistoryRecoResultBox(jobId, payload, jobMeta);
          wireHistoryRecoResultBox(box, jobId);
          box.classList.remove("muted");
          box.setAttribute("data-loaded", "1");
        } catch (e) {
          box.innerHTML = `${pill("failed")} ${escapeHtml(String(e.message || e))}`;
          box.setAttribute("data-loaded", "0");
        }
      });
    });
    list.querySelectorAll(".btn-toggle-reco-log").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const jobId = btn.getAttribute("data-job") || "";
        if (!jobId) return;

        const row = Array.from(list.querySelectorAll("tr.history-reco-log-row")).find((tr) => tr.getAttribute("data-job") === jobId);
        if (!row) return;

        const box = row.querySelector(".history-reco-log");
        if (!box) return;

        const isOpen = !row.classList.contains("hidden");
        if (isOpen) {
          row.classList.add("hidden");
          btn.textContent = t("btn_view_log");
          return;
        }

        row.classList.remove("hidden");
        btn.textContent = getLang() === "zh" ? "收起" : "Hide";

        if (box.getAttribute("data-loaded") === "1") return;
        box.textContent = t("loading");
        try {
          const text = await fetchJobLogIfNeeded(jobId);
          if (text == null) throw new Error(getLang() === "zh" ? "无法读取日志。" : "Failed to read log.");
          box.innerHTML = renderHistoryRecoLogBox(jobId, text);
          box.classList.remove("muted");
          box.setAttribute("data-loaded", "1");
        } catch (e) {
          box.innerHTML = `${pill("failed")} ${escapeHtml(String(e.message || e))}`;
          box.setAttribute("data-loaded", "0");
        }
      });
    });
    list.querySelectorAll(".btn-hide-job").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const jobId = btn.getAttribute("data-job") || "";
        if (!jobId) return;
        const ok = confirm(
          getLang() === "zh"
            ? `确定要隐藏该推荐任务吗？\n\njob_id=${jobId}\n\n说明：这是“软删除/隐藏”（可恢复），不会删除结果文件或日志文件。\n\n隐藏后它不会再出现在“经验反馈”的历史推荐列表中（除非你勾选“显示已隐藏”）。`
            : `Hide this recommendation job?\n\njob_id=${jobId}\n\nNote: this is a reversible soft-delete. It does not remove result/log files.\n\nIt will no longer show up in Feedback’s recommendation list unless you tick “Show hidden”.`
        );
        if (!ok) return;
        try {
          await apiJson(`/api/jobs/${encodeURIComponent(jobId)}/hide`, { method: "POST", body: JSON.stringify({}) });
          await refreshHistoryRecommendations();
          await refreshRecoList();
        } catch (e) {
          alert(String(e.message || e));
        }
      });
    });
    list.querySelectorAll(".btn-restore-job").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const jobId = btn.getAttribute("data-job") || "";
        if (!jobId) return;
        try {
          await apiJson(`/api/jobs/${encodeURIComponent(jobId)}/restore`, { method: "POST", body: JSON.stringify({}) });
          await refreshHistoryRecommendations();
          await refreshRecoList();
        } catch (e) {
          alert(String(e.message || e));
        }
      });
    });
  } catch (e) {
    list.innerHTML = `${pill("failed")} ${escapeHtml(String(e.message || e))}`;
  }
}

async function jumpToManualFeedback(recoJobId) {
  const jobId = String(recoJobId || "").trim();
  if (!jobId) return;

  window.location.hash = "#feedback";
  setActiveRoute("feedback");

  try {
    ensureManualGroupsInitialized();

    // Reuse an existing block if present; otherwise create a new block.
    let group = null;
    for (const gid of manualGroups) {
      const st = manualGroupStates[gid];
      if (st?.recoJobId === jobId) {
        group = st;
        break;
      }
    }
    if (!group) {
      group = createManualGroupCard();
      if (!group) throw new Error(getLang() === "zh" ? "无法创建反馈块（manual-groups 容器不存在）" : "Failed to create a manual feedback block.");
      const sel = group.el.querySelector("select.manual-group-reco");
      if (sel) sel.value = jobId;
      await loadRecoForManualGroup(group.groupId, jobId);
    }
    setManualGroupActive(group.groupId);
    group.el?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  } catch (e) {
    alert(String(e.message || e));
  }
}

function parseStepFromLog(text) {
  const matches = [...String(text || "").matchAll(/^\[(\d+)\/(\d+)\]\s*(.+)$/gm)];
  if (!matches.length) return null;
  const m = matches[matches.length - 1];
  return { cur: Number(m[1]), total: Number(m[2]), title: m[3] };
}

async function pollJob(jobId, onUpdate, { intervalMs = 1500, maxMs = 60 * 60 * 1000, alsoLog = false } = {}) {
  const start = Date.now();
  while (true) {
    const j = await apiJson(`/api/jobs/${jobId}`, { method: "GET", headers: {} });
    let logText = null;
    if (alsoLog) {
      try {
        logText = await apiText(`/api/jobs/${jobId}/log`);
      } catch {
        logText = null;
      }
    }
    onUpdate(j, logText);
    if (j.status === "completed" || j.status === "failed" || j.status === "cancelled") return j;
    if (Date.now() - start > maxMs) throw new Error("poll timeout");
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

async function refreshExperienceMeta() {
  const box = document.getElementById("experience-meta");
  if (!box) return;
  box.textContent = t("loading");
  try {
    const meta = await apiJson("/api/experience/meta", { method: "GET", headers: {} });
    const updated = meta.updated_at_utc || null;
    box.innerHTML = `
      ${pill("completed")}
      <b>experience.yaml</b><br/>
      updated_at_utc: <code>${escapeHtml(updated || "N/A")}</code><br/>
      ${t("beijing")}: <code>${escapeHtml(updated ? fmtBeijing(updated) : "N/A")}</code><br/>
      source_agent_yaml: <code>${escapeHtml(meta.source_agent_yaml || "N/A")}</code>
    `;
  } catch (e) {
    box.innerHTML = `${pill("failed")} ${escapeHtml(String(e.message || e))}`;
  }
}

function extractGuidelinesFromYaml(yamlText) {
  const lines = String(yamlText || "").split("\n");
  const out = [];
  let cur = null;
  const push = () => {
    if (cur && cur.id) out.push(cur);
    cur = null;
  };
  for (const line of lines) {
    const m = line.match(/^\s*\[G(\d+)\]\.\s*(.*)$/);
    if (m) {
      push();
      cur = { id: `G${m[1]}`, title: (m[2] || "").trim(), text: (m[2] || "").trim() };
      continue;
    }
    if (cur) {
      const s = line.replace(/^\s+/, "").trimEnd();
      if (s) cur.text += "\n" + s;
    }
  }
  push();
  return out;
}

function parseCaseCardLine(text) {
  const line = String(text || "").trim();
  const m = line.match(/^CaseCard\s*\|\s*(.*)$/i);
  if (!m) return null;
  const rest = m[1] || "";

  const keys = ["RT", "METALS", "TARGET", "ANCHOR", "TAKEAWAY", "APPLIES"];
  const re = new RegExp(`\\b(${keys.join("|")})=`, "g");
  const matches = [...rest.matchAll(re)];
  if (!matches.length) return null;

  const out = {};
  for (let i = 0; i < matches.length; i++) {
    const key = matches[i][1];
    const start = (matches[i].index ?? 0) + matches[i][0].length;
    const end = i + 1 < matches.length ? (matches[i + 1].index ?? rest.length) : rest.length;
    let val = rest.slice(start, end).trim();
    val = val.replace(/^[;\s]+/, "").replace(/[;\s]+$/, "");
    out[key] = val;
  }
  return out;
}

function renderMarkdownLite(text) {
  // A tiny "markdown-ish" renderer for our guideline texts:
  // - blank line => paragraph break
  // - lines starting with "- " or "* " => bullet list
  // - otherwise: join lines into a single paragraph (like markdown)
  const lines = String(text || "").split("\n");
  const blocks = [];
  let buf = [];

  const flush = () => {
    const raw = buf;
    buf = [];
    const nonEmpty = raw.map((x) => String(x || "").trim()).filter(Boolean);
    if (!nonEmpty.length) return;

    const listItems = nonEmpty.map((l) => {
      const m = l.match(/^[-*]\s+(.*)$/);
      return m ? m[1].trim() : null;
    });
    if (listItems.every((x) => x != null)) {
      blocks.push(`<ul>${listItems.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>`);
      return;
    }

    const para = nonEmpty
      .map((x) => x.replace(/\s+/g, " ").trim())
      .join(" ")
      .trim();
    if (!para) return;
    blocks.push(`<p>${escapeHtml(para)}</p>`);
  };

  for (const line of lines) {
    if (!String(line || "").trim()) {
      flush();
      continue;
    }
    buf.push(line);
  }
  flush();

  return blocks.join("");
}

function splitProseFirstParagraph(fullText) {
  const full = String(fullText || "").trim();
  if (!full) return { firstPara: "", restText: "" };

  const lines = full.split("\n");

  // First paragraph = until the first blank line.
  const paraLines = [];
  let i = 0;
  for (; i < lines.length; i++) {
    const s = String(lines[i] || "").trim();
    if (!s) break;
    paraLines.push(s);
  }

  // Everything after the first blank line (skip consecutive blanks).
  let restStart = i;
  while (restStart < lines.length && !String(lines[restStart] || "").trim()) restStart++;
  const restText = lines.slice(restStart).join("\n").trim();

  const firstPara = paraLines.join(" ").replace(/\s+/g, " ").trim();
  return { firstPara, restText };
}

function makeProsePreviewText(firstPara, restText, { maxChars = 200 } = {}) {
  const para = String(firstPara || "").replace(/\s+/g, " ").trim();
  const hasRest = Boolean(String(restText || "").trim());
  if (!para) return { preview: hasRest ? "…" : "", full: "", truncated: hasRest };

  // If we have more paragraphs, still hint "more" even if the first paragraph is short.
  if (para.length <= maxChars && !hasRest) return { preview: para, full: para, truncated: false };
  if (para.length <= maxChars && hasRest) return { preview: para + "…", full: para, truncated: true };

  // Character clamp with word-boundary preference.
  const slice = para.slice(0, maxChars);
  let cut = maxChars;
  const lastSpace = slice.lastIndexOf(" ");
  if (lastSpace >= Math.floor(maxChars * 0.6)) cut = lastSpace;
  cut = Math.max(0, cut);
  const preview = para.slice(0, cut).trimEnd() + "…";
  return { preview, full: para, truncated: true };
}

function wireGuidelineProseTitleToggles(containerEl) {
  const root = containerEl || document;
  root.querySelectorAll(".guideline-card-prose details").forEach((det) => {
    const title = det.querySelector("summary .guideline-title");
    if (!title) return;
    const full = title.getAttribute("data-full") || title.textContent || "";
    const preview = title.getAttribute("data-preview") || title.textContent || "";

    const sync = () => {
      title.textContent = det.open ? full : preview;
      title.setAttribute("title", det.open ? full : preview);
    };

    // Initialize and then keep in sync.
    sync();
    det.addEventListener("toggle", sync);
  });
}

function guidelineSummaryTitle(g) {
  const title = String(g?.title || "").trim();
  const full = String(g?.text || "").trim();
  const fields = parseCaseCardLine(title);
  if (!fields) {
    // Non-CaseCard: show the full first paragraph, but visually truncate via CSS when collapsed.
    const p = splitProseFirstParagraph(full);
    return p.firstPara || title || full;
  }
  const parts = ["CaseCard"];
  if (fields.RT) parts.push(fields.RT);
  if (fields.METALS) parts.push(fields.METALS);
  if (fields.TARGET) parts.push(fields.TARGET);
  return parts.join(" · ");
}

function renderGuidelineBodyHtml(g) {
  const full = String(g?.text || "").trim();
  const titleLine = String(g?.title || "").trim();
  const extra =
    titleLine && full.startsWith(titleLine) ? full.slice(titleLine.length).replace(/^\s*\n+/, "").trim() : "";

  const fields = parseCaseCardLine(titleLine || full);
  if (fields) {
    const labelTakeaway = getLang() === "zh" ? "经验要点" : "Takeaway";
    const labelApplies = getLang() === "zh" ? "适用条件" : "Applies";
    const more = extra ? `<div class="casecard-extra">${renderMarkdownLite(extra)}</div>` : "";
    return `
      <div class="md-block">
        <div class="casecard-grid">
          <div class="casecard-key">RT</div>
          <div class="casecard-val"><code class="casecard-val-text" title="${escapeHtml(fields.RT || "—")}">${escapeHtml(fields.RT || "—")}</code></div>
          <div class="casecard-key">METALS</div>
          <div class="casecard-val"><code class="casecard-val-text" title="${escapeHtml(fields.METALS || "—")}">${escapeHtml(fields.METALS || "—")}</code></div>
          <div class="casecard-key">TARGET</div>
          <div class="casecard-val"><code class="casecard-val-text" title="${escapeHtml(fields.TARGET || "—")}">${escapeHtml(fields.TARGET || "—")}</code></div>
          <div class="casecard-key">ANCHOR</div>
          <div class="casecard-val"><span class="casecard-val-text" title="${escapeHtml(fields.ANCHOR || "—")}">${escapeHtml(fields.ANCHOR || "—")}</span></div>
        </div>
        <div class="casecard-takeaway"><b>${escapeHtml(labelTakeaway)}</b>: ${escapeHtml(fields.TAKEAWAY || "—")}</div>
        <div class="casecard-applies muted"><b>${escapeHtml(labelApplies)}</b>: ${escapeHtml(fields.APPLIES || "—")}</div>
        ${more}
      </div>
    `;
  }

  // Non-CaseCard:
  // - Summary shows the first paragraph (visually clamped via CSS when collapsed).
  // - Body shows only the remaining paragraphs (no repetition, no "mid-word continuation").
  const p = splitProseFirstParagraph(full);
  if (!p.restText) return "";
  const html = renderMarkdownLite(p.restText);
  return `<div class="md-block">${html || `<span class="muted">${escapeHtml(t("empty"))}</span>`}</div>`;
}

function renderGuidelineDetailsHtml(g) {
  const isCaseCard = Boolean(parseCaseCardLine(String(g?.title || "").trim()));
  const cardCls = isCaseCard ? "card small guideline-card guideline-card-casecard" : "card small guideline-card guideline-card-prose";
  const title = isCaseCard ? guidelineSummaryTitle(g) : "";

  let proseTitleHtml = "";
  if (!isCaseCard) {
    const p = splitProseFirstParagraph(String(g?.text || ""));
    const prev = makeProsePreviewText(p.firstPara, p.restText, { maxChars: EXPERIENCE_PROSE_PREVIEW_MAX_CHARS });
    const previewText = prev.preview || p.firstPara || "";
    const fullText = prev.full || p.firstPara || "";
    proseTitleHtml = `<span class="guideline-title" data-preview="${escapeHtml(previewText)}" data-full="${escapeHtml(fullText)}" title="${escapeHtml(previewText)}">${escapeHtml(previewText)}</span>`;
  }

  return `
    <div class="${cardCls}">
      <details class="details">
        <summary>
          <code>[${escapeHtml(g.id)}]</code>
          ${isCaseCard ? `<span class="guideline-title" title="${escapeHtml(title || "")}">${escapeHtml(title || "")}</span>` : proseTitleHtml}
        </summary>
        ${renderGuidelineBodyHtml(g)}
      </details>
    </div>
  `;
}

async function renderExperienceCurrent() {
  const box = document.getElementById("experience-current-guidelines");
  const rawPre = document.getElementById("experience-current-raw");
  if (!box || !rawPre) return;
  try {
    const raw = await apiText("/api/experience/pack");
    rawPre.textContent = raw || t("empty");
    const gs = extractGuidelinesFromYaml(raw);
    experienceCurrentCache = { raw, guidelines: gs };
    if (!gs.length) {
      box.innerHTML = `<div class="muted">${escapeHtml(t("no_guidelines"))}</div>`;
      return;
    }
    renderExperienceCurrentFromCache();
  } catch (e) {
    box.innerHTML = `<div class="muted">${escapeHtml(String(e.message || e))}</div>`;
  }
}

function normalizeSearchTokens(q) {
  const s = String(q || "")
    .trim()
    .toLowerCase();
  if (!s) return [];
  return s
    .split(/[\s,;]+/g)
    .map((x) => x.trim())
    .filter(Boolean);
}

function guidelineSearchBlob(g) {
  const id = String(g?.id || "").trim();
  const title = String(g?.title || "").trim();
  const text = String(g?.text || "").trim();
  const fields = parseCaseCardLine(title);
  if (fields) {
    return (
      [
        id,
        "CaseCard",
        fields.RT || "",
        fields.METALS || "",
        fields.TARGET || "",
        fields.ANCHOR || "",
        fields.TAKEAWAY || "",
        fields.APPLIES || "",
        text,
      ]
        .join(" ")
        .toLowerCase() || ""
    );
  }
  return `${id}\n${title}\n${text}`.toLowerCase();
}

function filterGuidelines(gs, q) {
  const items = Array.isArray(gs) ? gs : [];
  const tokens = normalizeSearchTokens(q);
  if (!tokens.length) return items;
  return items.filter((g) => {
    const blob = guidelineSearchBlob(g);
    return tokens.every((tok) => blob.includes(tok));
  });
}

function renderExperienceCurrentFromCache() {
  const box = document.getElementById("experience-current-guidelines");
  const countEl = document.getElementById("experience-search-count");
  const pager = document.getElementById("experience-pagination");
  if (!box) return;

  const q = String(document.getElementById("experience-search")?.value || "");
  const all = experienceCurrentCache?.guidelines || [];
  const filtered = filterGuidelines(all, q);
  const pageSize = getExperiencePageSize();
  const total = Array.isArray(filtered) ? filtered.length : 0;
  const totalPages = Math.max(1, Math.ceil(total / Math.max(1, pageSize)));
  let page = getExperiencePage();
  if (page > totalPages) page = totalPages;
  if (page < 1) page = 1;
  setExperiencePage(page);

  const start = (page - 1) * pageSize;
  const end = Math.min(total, start + pageSize);
  const slice = total ? filtered.slice(start, end) : [];

  if (!slice.length) {
    box.innerHTML = `<div class="muted">${escapeHtml(getLang() === "zh" ? "没有匹配的经验条目。" : "No matching guideline items.")}</div>`;
  } else {
    box.innerHTML = slice.map((g) => renderGuidelineDetailsHtml(g)).join("");
    wireGuidelineProseTitleToggles(box);
  }

  if (countEl) {
    const a = Array.isArray(all) ? all.length : 0;
    const b = Array.isArray(filtered) ? filtered.length : 0;
    const qp = String(q || "").trim();
    countEl.textContent =
      getLang() === "zh"
        ? `显示 ${b}/${a} 条（搜索：${qp ? qp : "无"}） · 第 ${page}/${totalPages} 页 · 每页 ${pageSize} 条`
        : `Showing ${b}/${a} (query: ${qp ? qp : "none"}) · Page ${page}/${totalPages} · ${pageSize}/page`;
  }

  if (pager) {
    const prevLabel = getLang() === "zh" ? "上一页" : "Prev";
    const nextLabel = getLang() === "zh" ? "下一页" : "Next";
    const perPageLabel = getLang() === "zh" ? "每页" : "Per page";
    const pageLabel = getLang() === "zh" ? "页" : "Page";

    pager.innerHTML = `
      <button type="button" class="secondary" id="btn-exp-prev" ${page <= 1 ? "disabled" : ""}>${escapeHtml(prevLabel)}</button>
      <button type="button" class="secondary" id="btn-exp-next" ${page >= totalPages ? "disabled" : ""}>${escapeHtml(nextLabel)}</button>
      <span class="muted">${escapeHtml(pageLabel)} <code>${escapeHtml(String(page))}</code>/<code>${escapeHtml(String(totalPages))}</code></span>
      <span class="muted">${escapeHtml(perPageLabel)}</span>
      <select class="select" id="exp-page-size">
        ${EXPERIENCE_PAGE_SIZES.map((n) => `<option value="${n}" ${n === pageSize ? "selected" : ""}>${n}</option>`).join("")}
      </select>
    `;

    pager.querySelector("#btn-exp-prev")?.addEventListener("click", () => {
      setExperiencePage(Math.max(1, page - 1));
      renderExperienceCurrentFromCache();
    });
    pager.querySelector("#btn-exp-next")?.addEventListener("click", () => {
      setExperiencePage(Math.min(totalPages, page + 1));
      renderExperienceCurrentFromCache();
    });
    pager.querySelector("#exp-page-size")?.addEventListener("change", (e) => {
      setExperiencePageSize(e.target.value);
      setExperiencePage(1);
      renderExperienceCurrentFromCache();
    });
  }
}

async function renderExperienceHistory() {
  const box = document.getElementById("experience-history");
  if (!box) return;
  box.textContent = t("loading");
  try {
    const data = await apiJson("/api/experience/history", { method: "GET", headers: {} });
    const items = data.items || [];
    if (!items.length) {
      box.textContent = t("empty");
      return;
    }
    box.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>updated_at_utc</th>
            <th>${escapeHtml(t("beijing"))}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          ${items
            .map((it) => {
              const updated = it.updated_at_utc || it.mtime_utc || "";
              const bj = updated ? fmtBeijing(updated) : "";
              return `
                <tr>
                  <td><code>${escapeHtml(it.id)}</code></td>
                  <td><code>${escapeHtml(updated)}</code></td>
                  <td><code>${escapeHtml(bj)}</code></td>
                  <td class="row">
                    <button type="button" class="secondary btn-activate-archive" data-archive="${escapeHtml(it.id)}">${escapeHtml(t("activate"))}</button>
                    <button type="button" class="secondary btn-view-archive" data-archive="${escapeHtml(it.id)}">${escapeHtml(t("view"))}</button>
                    <a class="secondary" href="${escapeHtml(it.download_url)}" target="_blank" rel="noreferrer">${escapeHtml(t("download"))}</a>
                  </td>
                </tr>
              `;
            })
            .join("")}
        </tbody>
      </table>
    `;

    box.querySelectorAll(".btn-activate-archive").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-archive");
        if (!id) return;
        await activateArchivePack(id);
      });
    });
    box.querySelectorAll(".btn-view-archive").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-archive");
        if (!id) return;
        await viewArchivePack(id);
      });
    });
  } catch (e) {
    box.textContent = `Failed: ${String(e.message || e)}`;
  }
}

async function activateArchivePack(archiveId) {
  const ok = confirm(
    getLang() === "zh"
      ? `确定要切换当前生效的经验库到该历史版本吗？\n\narchive_id=${archiveId}\n\n提示：系统会自动把“当前版本”先备份到 archive 里，方便你再切回来。`
      : `Activate this archived experience pack?\n\narchive_id=${archiveId}\n\nNote: the current pack will be backed up into the archive first, so you can switch back later.`
  );
  if (!ok) return;

  try {
    const res = await apiJson(`/api/experience/activate/${encodeURIComponent(archiveId)}`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    const backup = res.backup_archive_id ? `backup=${res.backup_archive_id}` : "backup=(none)";
    alert(
      getLang() === "zh"
        ? `已切换经验库：${archiveId}\n${backup}\n\nupdated_at_utc=${res.updated_at_utc || "N/A"}`
        : `Activated: ${archiveId}\n${backup}\n\nupdated_at_utc=${res.updated_at_utc || "N/A"}`
    );
  } catch (e) {
    alert(String(e.message || e));
  } finally {
    await refreshExperienceMeta();
    await renderExperienceHistory();
    await renderExperienceCurrent();
  }
}

async function viewArchivePack(archiveId) {
  const view = document.getElementById("experience-history-view");
  if (!view) return;
  view.classList.remove("hidden");
  view.textContent = t("loading");
  try {
    const raw = await apiText(`/api/experience/history/${encodeURIComponent(archiveId)}/pack`);
    const gs = extractGuidelinesFromYaml(raw);
    view.innerHTML = `
      <div class="row">
        <b>${escapeHtml(getLang() === "zh" ? "历史经验库" : "Archived pack")}</b>
        <code>${escapeHtml(archiveId)}</code>
        <button type="button" class="secondary btn-activate-archive-view" data-archive="${escapeHtml(archiveId)}">${escapeHtml(t("activate"))}</button>
        <a class="secondary" href="/api/experience/history/${encodeURIComponent(archiveId)}/pack" target="_blank" rel="noreferrer">${escapeHtml(t("download"))}</a>
      </div>
      <div class="stack">
        ${gs.map((g) => renderGuidelineDetailsHtml(g)).join("")}
        <details class="details">
          <summary>${escapeHtml(getLang() === "zh" ? "原始 YAML" : "Raw YAML")}</summary>
          <pre class="log">${escapeHtml(raw)}</pre>
        </details>
      </div>
    `;
    wireGuidelineProseTitleToggles(view);
    view.querySelectorAll(".btn-activate-archive-view").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-archive");
        if (!id) return;
        await activateArchivePack(id);
      });
    });
  } catch (e) {
    view.innerHTML = `${pill("failed")} ${escapeHtml(String(e.message || e))}`;
  }
}

function renderRankResult(jobId, payload, jobMeta = null) {
  return renderHistoryRecoResultBox(jobId, payload, jobMeta);
}

function renderUpdateResult(payload) {
  const updatedUtc = payload.updated_at_utc || null;
  return `
    <div class="row">
      ${pill("completed")} <b>${escapeHtml(getLang() === "zh" ? "经验库已更新" : "Experience updated")}</b>
      <a class="secondary" href="/api/experience/pack" target="_blank" rel="noreferrer">${escapeHtml(getLang() === "zh" ? "下载当前 experience.yaml" : "Download current experience.yaml")}</a>
    </div>
    <div class="stack">
      <div>dataset_name: <code>${escapeHtml(payload.dataset_name || "")}</code></div>
      <div>num_samples: <code>${escapeHtml(payload.num_samples || "")}</code></div>
      <div>exp_id: <code>${escapeHtml(payload.exp_id || "")}</code></div>
      <div>updated_at_utc: <code>${escapeHtml(updatedUtc || "N/A")}</code></div>
      <div>${escapeHtml(t("beijing"))}: <code>${escapeHtml(updatedUtc ? fmtBeijing(updatedUtc) : "N/A")}</code></div>
    </div>
  `;
}

function meanNumber(xs) {
  const vals = (Array.isArray(xs) ? xs : []).map((x) => Number(x)).filter((x) => Number.isFinite(x));
  if (!vals.length) return null;
  return vals.reduce((a, b) => a + b, 0) / vals.length;
}

function stdNumber(xs) {
  const vals = (Array.isArray(xs) ? xs : []).map((x) => Number(x)).filter((x) => Number.isFinite(x));
  if (vals.length < 2) return 0;
  const m = meanNumber(vals);
  if (m == null) return 0;
  const v = vals.reduce((acc, x) => acc + (x - m) * (x - m), 0) / vals.length;
  return Math.sqrt(Math.max(0, v));
}

function analysisAggHint(kind, step) {
  const n = Math.max(1, Number(step || 1));
  if (kind === "rounds") {
    return getLang() === "zh"
      ? "每个点代表一次“反馈更新”（上传/手动提交）整体的平均相对误差。"
      : "Each point is one feedback update round (mean relative error of that upload/submission).";
  }
  if (kind === "records_cumulative") {
    return getLang() === "zh"
      ? `累计模式：用 1–${n}、1–${n * 2}、1–${n * 3}… 条评估记录的累计平均相对误差画趋势（适合看长期是否变好）。`
      : `Cumulative mode: plot the cumulative mean relative error over 1–${n}, 1–${n * 2}, 1–${n * 3}… analytics records (good for long-term trends).`;
  }
  return getLang() === "zh"
    ? `分桶模式：每 ${n} 条评估记录聚合成 1 个点（非重叠），计算该桶的平均相对误差（±1σ）。建议用 ${FIXED_UPDATE_BATCH_SIZE}（与 batch_size 对齐）。`
    : `Bucket mode: every ${n} analytics record(s) become 1 point (non-overlapping). We plot mean relative error (±1σ). Consider ${FIXED_UPDATE_BATCH_SIZE} to align with batch_size.`;
}

function sortAnalysisRecords(records) {
  const recs = Array.isArray(records) ? [...records] : [];
  recs.sort((a, b) => {
    const ta = String(a?.update_finished_at_utc || a?.recommendation_finished_at_utc || "");
    const tb = String(b?.update_finished_at_utc || b?.recommendation_finished_at_utc || "");
    if (ta !== tb) return ta.localeCompare(tb);
    const ja = String(a?.update_job_id || "");
    const jb = String(b?.update_job_id || "");
    if (ja !== jb) return ja.localeCompare(jb);
    return 0;
  });
  return recs;
}

function isIgnoredRecord(r) {
  return Boolean(r && r.ignored);
}

function buildAnalysisPoints({ rounds, records }, { kind, step }) {
  const k = kind || "records_bucket";
  const n = Math.max(1, Number(step || FIXED_UPDATE_BATCH_SIZE));

  if (k === "rounds") {
    const pts = Array.isArray(rounds)
      ? rounds.filter((x) => x && x.mean_rel_error != null && Number.isFinite(Number(x.mean_rel_error)))
      : [];
    const recs = sortAnalysisRecords(records).filter((r) => r && r.rel_error != null && Number.isFinite(Number(r.rel_error)));
    return pts.map((r) => {
      const rid = String(r.round_index ?? "");
      const label = getLang() === "zh" ? `回合 ${rid}` : `Round ${rid}`;
      const jobId = String(r.update_job_id || "");
      const chunk = recs.filter((x) => String(x.update_job_id || "") === jobId);
      const included = chunk.filter((x) => !isIgnoredRecord(x));
      const rels = included.map((x) => Number(x.rel_error)).filter((x) => Number.isFinite(x));
      const std = rels.length ? stdNumber(rels) : 0;
      return {
        label,
        mean_rel_error: r.mean_rel_error != null ? Number(r.mean_rel_error) : null,
        std_rel_error: Number.isFinite(Number(std)) ? Number(std) : 0,
        n_records: r.num_records != null ? Number(r.num_records) : rels.length,
        n_records_total: chunk.length,
        n_records_ignored: Math.max(0, chunk.length - rels.length),
        update_job_id: jobId,
        update_finished_at_utc: r.update_finished_at_utc != null ? String(r.update_finished_at_utc) : null,
        components: String(r.components || ""),
        round_index: r.round_index != null ? Number(r.round_index) : null,
      };
    });
  }

  const recs = sortAnalysisRecords(records).filter((r) => r && r.rel_error != null && Number.isFinite(Number(r.rel_error)));
  if (!recs.length) return [];

  const pts = [];
  if (k === "records_cumulative") {
    for (let end = n; end <= recs.length; end += n) {
      const chunk = recs.slice(0, end);
      const included = chunk.filter((x) => !isIgnoredRecord(x));
      const rels = included.map((x) => Number(x.rel_error)).filter((x) => Number.isFinite(x));
      const std = rels.length ? stdNumber(rels) : 0;
      pts.push({
        label: `1-${end}`,
        mean_rel_error: meanNumber(rels),
        std_rel_error: Number.isFinite(Number(std)) ? Number(std) : 0,
        n_records: included.length,
        n_records_total: chunk.length,
        n_records_ignored: Math.max(0, chunk.length - included.length),
        update_job_id: String(chunk[chunk.length - 1]?.update_job_id || ""),
        update_finished_at_utc: chunk[chunk.length - 1]?.update_finished_at_utc ? String(chunk[chunk.length - 1]?.update_finished_at_utc) : null,
      });
    }
    if (recs.length % n !== 0) {
      const end = recs.length;
      const included = recs.filter((x) => !isIgnoredRecord(x));
      const rels = included.map((x) => Number(x.rel_error)).filter((x) => Number.isFinite(x));
      const std = rels.length ? stdNumber(rels) : 0;
      pts.push({
        label: `1-${end}`,
        mean_rel_error: meanNumber(rels),
        std_rel_error: Number.isFinite(Number(std)) ? Number(std) : 0,
        n_records: included.length,
        n_records_total: recs.length,
        n_records_ignored: Math.max(0, recs.length - included.length),
        update_job_id: String(recs[recs.length - 1]?.update_job_id || ""),
        update_finished_at_utc: recs[recs.length - 1]?.update_finished_at_utc ? String(recs[recs.length - 1]?.update_finished_at_utc) : null,
      });
    }
    return pts.filter((p) => p.mean_rel_error != null);
  }

  // records_bucket (default)
  for (let start = 0; start < recs.length; start += n) {
    const chunk = recs.slice(start, start + n);
    if (!chunk.length) continue;
    const left = start + 1;
    const right = start + chunk.length;
    const included = chunk.filter((x) => !isIgnoredRecord(x));
    const rels = included.map((x) => Number(x.rel_error)).filter((x) => Number.isFinite(x));
    const std = rels.length ? stdNumber(rels) : 0;
    pts.push({
      label: `${left}-${right}`,
      mean_rel_error: meanNumber(rels),
      std_rel_error: Number.isFinite(Number(std)) ? Number(std) : 0,
      n_records: included.length,
      n_records_total: chunk.length,
      n_records_ignored: Math.max(0, chunk.length - included.length),
      update_job_id: String(chunk[chunk.length - 1]?.update_job_id || ""),
      update_finished_at_utc: chunk[chunk.length - 1]?.update_finished_at_utc ? String(chunk[chunk.length - 1]?.update_finished_at_utc) : null,
    });
  }
  return pts.filter((p) => p.mean_rel_error != null);
}

function fmtRel(x) {
  const v = Number(x);
  if (!Number.isFinite(v)) return "—";
  if (v === 0) return "0";
  if (Math.abs(v) >= 10) return v.toFixed(1);
  if (Math.abs(v) >= 1) return v.toFixed(2);
  return v.toFixed(3);
}

function niceNum(range, round) {
  const r = Math.abs(Number(range));
  if (!Number.isFinite(r) || r === 0) return 1;
  const exp = Math.floor(Math.log10(r));
  const f = r / Math.pow(10, exp);
  let nf;
  if (round) {
    if (f < 1.5) nf = 1;
    else if (f < 3) nf = 2;
    else if (f < 7) nf = 5;
    else nf = 10;
  } else {
    if (f <= 1) nf = 1;
    else if (f <= 2) nf = 2;
    else if (f <= 5) nf = 5;
    else nf = 10;
  }
  return nf * Math.pow(10, exp);
}

function niceTicks(min, max, maxTicks = 5) {
  const lo = Number(min);
  const hi = Number(max);
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return [0, 1];
  const span = Math.max(1e-12, hi - lo);
  const rng = niceNum(span, false);
  const step = niceNum(rng / Math.max(1, maxTicks - 1), true);
  const graphMin = Math.floor(lo / step) * step;
  const graphMax = Math.ceil(hi / step) * step;
  const out = [];
  for (let v = graphMin; v <= graphMax + step * 0.5; v += step) out.push(v);
  return out;
}

function chooseXTicks(nPoints, maxTicks = 10) {
  const n = Math.max(0, Number(nPoints || 0));
  if (n <= maxTicks) return Array.from({ length: n }, (_, i) => i);
  const step = Math.ceil((n - 1) / Math.max(1, maxTicks - 1));
  const idx = [];
  for (let i = 0; i < n; i += step) idx.push(i);
  if (idx[idx.length - 1] !== n - 1) idx.push(n - 1);
  return idx;
}

function renderRelErrorLineChart(points, { title, subtitle, xLabel, yLabel } = {}) {
  const pts = Array.isArray(points)
    ? points.filter((x) => x && x.mean_rel_error != null && Number.isFinite(Number(x.mean_rel_error)))
    : [];
  if (!pts.length) return "";

  const W = 760;
  const H = 260;
  const padL = 62;
  const padR = 16;
  const padT = 18;
  const padB = 64;

  const yMin = 0;
  const yMaxRaw = Math.max(
    0,
    ...pts.map((p) => {
      const m = Number(p.mean_rel_error);
      const s = Number(p.std_rel_error || 0);
      if (!Number.isFinite(m)) return 0;
      return m + (Number.isFinite(s) ? s : 0);
    })
  );
  const yMax = yMaxRaw > 0 ? yMaxRaw * 1.12 : 1;
  const ySpan = Math.max(1e-9, yMax - yMin);

  const xTo = (i) => padL + (i * (W - padL - padR)) / Math.max(1, pts.length - 1);
  const yTo = (y) => padT + (1 - (y - yMin) / ySpan) * (H - padT - padB);

  const path = pts
    .map((p, i) => {
      const x = xTo(i).toFixed(1);
      const y = yTo(Number(p.mean_rel_error)).toFixed(1);
      return `${i === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .join(" ");

  const errBars = pts
    .map((p, i) => {
      const mean = Number(p.mean_rel_error);
      if (!Number.isFinite(mean)) return "";
      const std = Math.max(0, Number(p.std_rel_error || 0));
      if (!Number.isFinite(std) || std <= 0) return "";
      const x = xTo(i).toFixed(1);
      const lo = Math.max(yMin, mean - std);
      const hi = mean + std;
      const y1 = yTo(lo).toFixed(1);
      const y2 = yTo(hi).toFixed(1);
      const cap = 5.2;
      return `
        <line x1="${x}" y1="${y1}" x2="${x}" y2="${y2}" stroke="var(--muted)" stroke-width="1.2" />
        <line x1="${(Number(x) - cap).toFixed(1)}" y1="${y1}" x2="${(Number(x) + cap).toFixed(1)}" y2="${y1}" stroke="var(--muted)" stroke-width="1.2" />
        <line x1="${(Number(x) - cap).toFixed(1)}" y1="${y2}" x2="${(Number(x) + cap).toFixed(1)}" y2="${y2}" stroke="var(--muted)" stroke-width="1.2" />
      `;
    })
    .join("");

  const dots = pts
    .map((p, i) => {
      const x = xTo(i).toFixed(1);
      const y = yTo(Number(p.mean_rel_error)).toFixed(1);
      const rel = fmtRel(p.mean_rel_error);
      const std = fmtRel(p.std_rel_error || 0);
      const nIn = p.n_records != null ? Number(p.n_records) : null;
      const nTot = p.n_records_total != null ? Number(p.n_records_total) : null;
      const n =
        nIn == null
          ? "—"
          : nTot != null && Number.isFinite(nTot) && nTot !== nIn
            ? `${nIn}/${nTot}`
            : String(nIn);
      const when = p.update_finished_at_utc ? fmtBeijing(String(p.update_finished_at_utc)) : "—";
      const tip = `${p.label} | mean_rel_error=${rel} ± ${std} (1σ) | n=${n} | updated=${when}`;
      return `<circle cx="${x}" cy="${y}" r="3.7" fill="var(--accent)"><title>${escapeHtml(tip)}</title></circle>`;
    })
    .join("");

  const yTicks = niceTicks(yMin, yMax, 5);
  const yGrid = yTicks
    .map((v) => {
      const y = yTo(v).toFixed(1);
      const lbl = fmtRel(v);
      return `
        <line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="var(--border)" stroke-width="1" opacity="0.35" />
        <text x="${padL - 8}" y="${(Number(y) + 3.5).toFixed(1)}" text-anchor="end" font-size="11" fill="var(--muted)">${escapeHtml(lbl)}</text>
      `;
    })
    .join("");

  const xTicks = chooseXTicks(pts.length, 10)
    .map((i) => {
      const x = xTo(i).toFixed(1);
      const lblRaw = String(pts[i]?.label || "");
      const lbl = lblRaw.length > 10 ? lblRaw.slice(0, 10) + "…" : lblRaw;
      return `
        <line x1="${x}" y1="${H - padB}" x2="${x}" y2="${H - padB + 5}" stroke="var(--border)" stroke-width="1" />
        <text x="${x}" y="${H - padB + 18}" text-anchor="middle" font-size="11" fill="var(--muted)">${escapeHtml(lbl)}</text>
      `;
    })
    .join("");

  const titleLine = title ? `<b>${escapeHtml(title)}</b>` : "";
  const subLine = subtitle ? `<div class="hint muted">${escapeHtml(subtitle)}</div>` : "";
  const xLbl = xLabel ? `<text x="${((padL + (W - padR)) / 2).toFixed(1)}" y="${H - 10}" text-anchor="middle" font-size="12" fill="var(--muted)">${escapeHtml(xLabel)}</text>` : "";
  const yLbl = yLabel
    ? `<text x="14" y="${((padT + (H - padB)) / 2).toFixed(1)}" text-anchor="middle" font-size="12" fill="var(--muted)" transform="rotate(-90 14 ${((padT + (H - padB)) / 2).toFixed(1)})">${escapeHtml(yLabel)}</text>`
    : "";

  return `
    <div class="row">${titleLine}</div>
    ${subLine}
    <svg viewBox="0 0 ${W} ${H}" width="100%" height="280" role="img" aria-label="relative error chart">
      <rect x="0" y="0" width="${W}" height="${H}" fill="transparent" />
      ${yGrid}
      <line x1="${padL}" y1="${H - padB}" x2="${W - padR}" y2="${H - padB}" stroke="var(--border)" stroke-width="1.2" />
      <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${H - padB}" stroke="var(--border)" stroke-width="1.2" />
      ${xTicks}
      ${yLbl}
      ${xLbl}
      ${errBars}
      <path d="${path}" fill="none" stroke="var(--accent)" stroke-width="2.2" />
      ${dots}
    </svg>
  `;
}

function renderAnalysisAggTable(points, { kind } = {}) {
  const pts = Array.isArray(points) ? points : [];
  if (!pts.length) return "";

  const k = kind || "records_bucket";
  const isRounds = k === "rounds";

  const headLabel = escapeHtml(
    getLang() === "zh"
      ? isRounds
        ? "回合"
        : k === "records_cumulative"
          ? "累计区间"
          : "记录区间"
      : isRounds
        ? "Round"
        : k === "records_cumulative"
          ? "Cumulative range"
          : "Record range"
  );
  const headTime = escapeHtml(getLang() === "zh" ? "更新时间（北京时间）" : "Updated (CST)");
  const headN = escapeHtml(getLang() === "zh" ? "记录数" : "N");
  const headRel = escapeHtml(getLang() === "zh" ? "平均相对误差" : "Mean rel error");
  const headStd = escapeHtml(getLang() === "zh" ? "误差棒(±1σ)" : "Error bar (±1σ)");
  const headComp = escapeHtml(getLang() === "zh" ? "材料/检索元素" : "Material/retrieval elements");
  const headJob = escapeHtml(getLang() === "zh" ? "更新任务ID" : "Update job id");
  const headAct = escapeHtml(getLang() === "zh" ? "操作" : "Actions");

  const rows = pts
    .map((p) => {
      const when = p.update_finished_at_utc ? fmtBeijing(String(p.update_finished_at_utc)) : "—";
      const nIn = p.n_records != null ? Number(p.n_records) : 0;
      const nTot = p.n_records_total != null ? Number(p.n_records_total) : null;
      const n =
        nTot != null && Number.isFinite(nTot) && nTot !== nIn
          ? `${nIn}/${nTot}`
          : String(nIn);
      const rel = fmtRel(p.mean_rel_error);
      const std = fmtRel(p.std_rel_error || 0);
      const label = String(p.round_index != null ? p.round_index : p.label || "");
      const comps = String(p.components || "");
      const short = comps.length > 44 ? comps.slice(0, 44) + "…" : comps;
      const jid = String(p.update_job_id || "").trim();
      const btn = isRounds
        ? `<button type="button" class="secondary btn-hide-round" data-job="${escapeHtml(jid)}">${escapeHtml(t("btn_hide_round"))}</button>`
        : "";

      return `
        <tr>
          <td><code>${escapeHtml(label)}</code></td>
          <td><code>${escapeHtml(when)}</code></td>
          <td><code>${escapeHtml(n)}</code></td>
          <td><code>${escapeHtml(rel)}</code></td>
          <td><code>${escapeHtml(std)}</code></td>
          ${
            isRounds
              ? `<td class="muted">${escapeHtml(short)}</td><td class="row">${btn}</td>`
              : `<td><code>${escapeHtml(jid)}</code></td>`
          }
        </tr>
      `;
    })
    .join("");

  const cols = isRounds
    ? `<th>${headLabel}</th><th>${headTime}</th><th>${headN}</th><th>${headRel}</th><th>${headStd}</th><th>${headComp}</th><th>${headAct}</th>`
    : `<th>${headLabel}</th><th>${headTime}</th><th>${headN}</th><th>${headRel}</th><th>${headStd}</th><th>${headJob}</th>`;

  return `
    <div class="table-wrap">
      <table class="table">
        <thead><tr>${cols}</tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function fmtVal(x) {
  const v = Number(x);
  if (!Number.isFinite(v)) return "—";
  const a = Math.abs(v);
  if (v === 0) return "0";
  if (a >= 1000) return v.toFixed(0);
  if (a >= 100) return v.toFixed(1).replace(/\.0$/, "");
  if (a >= 10) return v.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
  if (a >= 1) return v.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
  return v.toPrecision(3);
}

function formatAnalyticsMetricLabel(metricKey) {
  const key = String(metricKey || "").trim();
  if (!key) return "—";
  const labels = {
    photothermal_conversion_efficiency: ["光热转换效率", "Photothermal conversion efficiency"],
    conductivity: ["电导率", "Electrical conductivity"],
    thermal_conductivity: ["热导率", "Thermal conductivity"],
    saturation_magnetization: ["饱和磁化强度", "Saturation magnetization"],
    neel_temperature: ["尼尔温度", "Neel temperature"],
  };
  if (labels[key]) return getLang() === "zh" ? labels[key][0] : labels[key][1];
  return key;
}

function getAnalysisCellText(record, kind) {
  const rec = record || {};
  const displayKey = `${kind}_display`;
  const displayValue = rec[displayKey];
  if (typeof displayValue === "string" && displayValue.trim()) return displayValue.trim();
  const unit = String(rec.unit || "").trim();
  if (kind === "predicted") return `${fmtVal(rec.predicted_value)} ${unit}`.trim();
  if (kind === "actual") return `${fmtVal(rec.actual_value)} ${unit}`.trim();
  if (kind === "abs_error") return `${fmtVal(rec.abs_error)} ${unit}`.trim();
  return "—";
}

function shortId(id, n = 8) {
  const s = String(id || "").trim();
  if (!s) return "—";
  if (s.length <= n) return s;
  return s.slice(0, n) + "…";
}

function validAnalysisRecords(records) {
  const recs = sortAnalysisRecords(records).filter((r) => r && r.rel_error != null && Number.isFinite(Number(r.rel_error)));
  return recs;
}

function buildAnalysisRecordGroups({ rounds, records }, { kind, step, points }) {
  const k = kind || "records_bucket";
  const n = Math.max(1, Number(step || FIXED_UPDATE_BATCH_SIZE));
  const recs = validAnalysisRecords(records);
  const groups = [];

  if (k === "rounds") {
    const pts = Array.isArray(points) ? points : [];
    for (const p of pts) {
      const jobId = String(p.update_job_id || "").trim();
      if (!jobId) continue;
      const chunk = recs.filter((r) => String(r.update_job_id || "").trim() === jobId);
      if (!chunk.length) continue;
      const included = chunk.filter((x) => !isIgnoredRecord(x));
      const rels = included.map((x) => Number(x.rel_error)).filter((x) => Number.isFinite(x));
      groups.push({
        label: String(p.label || ""),
        update_job_id: jobId,
        update_finished_at_utc: p.update_finished_at_utc || chunk[chunk.length - 1]?.update_finished_at_utc || null,
        n_records: included.length,
        n_records_total: chunk.length,
        n_records_ignored: Math.max(0, chunk.length - included.length),
        mean_rel_error: meanNumber(rels),
        std_rel_error: stdNumber(rels),
        records: chunk,
      });
    }
    return groups;
  }

  if (k === "records_cumulative") {
    // To avoid duplicating the same record in multiple cumulative points, we show incremental segments.
    // Each segment still depends on `step`, so switching view updates this table too.
    for (let start = 0; start < recs.length; start += n) {
      const chunk = recs.slice(start, start + n);
      if (!chunk.length) continue;
      const left = start + 1;
      const right = start + chunk.length;
      const cumRight = right;
      const label =
        getLang() === "zh"
          ? `新增 ${left}-${right}（累计到 1-${cumRight}）`
          : `Added ${left}-${right} (cumulative 1-${cumRight})`;
      const included = chunk.filter((x) => !isIgnoredRecord(x));
      const rels = included.map((x) => Number(x.rel_error)).filter((x) => Number.isFinite(x));
      groups.push({
        label,
        update_job_id: String(chunk[chunk.length - 1]?.update_job_id || ""),
        update_finished_at_utc: chunk[chunk.length - 1]?.update_finished_at_utc ? String(chunk[chunk.length - 1]?.update_finished_at_utc) : null,
        n_records: included.length,
        n_records_total: chunk.length,
        n_records_ignored: Math.max(0, chunk.length - included.length),
        mean_rel_error: meanNumber(rels),
        std_rel_error: stdNumber(rels),
        records: chunk,
      });
    }
    return groups;
  }

  // records_bucket (default): show the same non-overlapping buckets as the chart.
  for (let start = 0; start < recs.length; start += n) {
    const chunk = recs.slice(start, start + n);
    if (!chunk.length) continue;
    const left = start + 1;
    const right = start + chunk.length;
    const label = `${left}-${right}`;
    const included = chunk.filter((x) => !isIgnoredRecord(x));
    const rels = included.map((x) => Number(x.rel_error)).filter((x) => Number.isFinite(x));
    groups.push({
      label,
      update_job_id: String(chunk[chunk.length - 1]?.update_job_id || ""),
      update_finished_at_utc: chunk[chunk.length - 1]?.update_finished_at_utc ? String(chunk[chunk.length - 1]?.update_finished_at_utc) : null,
      n_records: included.length,
      n_records_total: chunk.length,
      n_records_ignored: Math.max(0, chunk.length - included.length),
      mean_rel_error: meanNumber(rels),
      std_rel_error: stdNumber(rels),
      records: chunk,
    });
  }
  return groups;
}

function renderAnalysisRecordsTable({ rounds, records }, { kind, step, points }) {
  const boxTitle = getLang() === "zh" ? "记录明细（预测 vs 实验）" : "Record details (prediction vs experiment)";
  const hint =
    kind === "records_cumulative"
      ? getLang() === "zh"
        ? "提示：累计模式下，为避免重复，这里展示的是“新增段”（每段 N 条），而图上是累计均值。"
        : "Note: in cumulative mode, to avoid duplication we show incremental segments (N records each), while the chart uses cumulative means."
      : getLang() === "zh"
        ? "提示：展开每个分组可查看逐条记录（任务方向、预测值、真实值、误差）。"
        : "Tip: expand each group to see per-record rows (direction, predicted, actual, errors).";

  const groups = buildAnalysisRecordGroups({ rounds, records }, { kind, step, points });
  if (!groups.length) return "";

  const showHideRound = kind === "rounds";

  const headIdx = escapeHtml(getLang() === "zh" ? "#" : "#");
  const headRt = escapeHtml(getLang() === "zh" ? "任务方向" : "Direction");
  const headMetric = escapeHtml(getLang() === "zh" ? "指标" : "Metric");
  const headPred = escapeHtml(getLang() === "zh" ? "预测值" : "Pred");
  const headAct = escapeHtml(getLang() === "zh" ? "真实值" : "Actual");
  const headAbs = escapeHtml(getLang() === "zh" ? "绝对误差" : "Abs err");
  const headRel = escapeHtml(getLang() === "zh" ? "相对误差" : "Rel err");
  const headReco = escapeHtml(getLang() === "zh" ? "推荐ID" : "Reco id");
  const headUpd = escapeHtml(getLang() === "zh" ? "更新ID" : "Update id");
  const headActions = escapeHtml(getLang() === "zh" ? "操作" : "Actions");

  const blocks = groups
    .map((g, gi) => {
      const when = g.update_finished_at_utc ? fmtBeijing(String(g.update_finished_at_utc)) : "—";
      const rel = fmtRel(g.mean_rel_error);
      const std = fmtRel(g.std_rel_error);
      const nIn = g.n_records != null ? Number(g.n_records) : Number((g.records || []).length || 0);
      const nTot = g.n_records_total != null ? Number(g.n_records_total) : nIn;
      const nIgnored = g.n_records_ignored != null ? Number(g.n_records_ignored) : Math.max(0, nTot - nIn);
      const nDisp = nTot !== nIn ? `${nIn}/${nTot}` : String(nIn);
      const ignoredDisp = nIgnored > 0 ? (getLang() === "zh" ? ` · 已忽略=${nIgnored}` : ` · ignored=${nIgnored}`) : "";
      const summary = `${g.label} · mean_rel_error=${rel} ± ${std} · n=${nDisp}${ignoredDisp} · updated=${when}`;
      const hideRoundHtml =
        showHideRound && String(g.update_job_id || "").trim()
          ? `
            <div class="row">
              <button type="button" class="secondary btn-hide-round" data-job="${escapeHtml(String(g.update_job_id || "").trim())}">
                ${escapeHtml(t("btn_hide_round"))}
              </button>
              <span class="muted">update_job_id: <code>${escapeHtml(String(g.update_job_id || "").trim())}</code></span>
            </div>
          `
          : "";
      const statsRow = `
        <tr>
          <th colspan="10" class="analysis-group-stats">
            ${escapeHtml(getLang() === "zh" ? "区间" : "Range")}: <code>${escapeHtml(String(g.label || ""))}</code> ·
            ${escapeHtml(getLang() === "zh" ? "平均相对误差" : "Mean rel error")}: <code>${escapeHtml(rel)}</code> ± <code>${escapeHtml(std)}</code> (1σ) ·
            ${escapeHtml(getLang() === "zh" ? "记录数" : "N")}: <code>${escapeHtml(nDisp)}</code>${nIgnored > 0 ? ` · ${escapeHtml(getLang() === "zh" ? "已忽略" : "Ignored")}: <code>${escapeHtml(String(nIgnored))}</code>` : ""} ·
            ${escapeHtml(getLang() === "zh" ? "更新时间" : "Updated")}: <code>${escapeHtml(when)}</code>
          </th>
        </tr>
      `;

      const rows = (Array.isArray(g.records) ? g.records : [])
        .map((r, i) => {
          const rt = String(r.reaction_type || "").trim();
          const metric = String(r.metric_key || "").trim();
          const metricLabel = formatAnalyticsMetricLabel(metric);
          const pred = getAnalysisCellText(r, "predicted");
          const act = getAnalysisCellText(r, "actual");
          const abs = getAnalysisCellText(r, "abs_error");
          const rel = fmtRel(r.rel_error);
          const recoId = String(r.recommendation_job_id || "").trim();
          const updId = String(r.update_job_id || "").trim();
          const csvRow = Number(r.csv_row_index);
          const ignored = isIgnoredRecord(r);
          const actionTitle = getLang() === "zh" ? "只影响效果评估统计，不会回滚经验库。" : "Affects Analytics only; does not roll back the experience pack.";
          const actionHtml = ignored
            ? `
              <span class="muted">(${escapeHtml(getLang() === "zh" ? "已忽略" : "Ignored")})</span>
              <button type="button" class="secondary btn-unignore-record" data-job="${escapeHtml(updId)}" data-row="${escapeHtml(String(csvRow))}" title="${escapeHtml(actionTitle)}">
                ${escapeHtml(t("btn_unignore_row"))}
              </button>
            `
            : `
              <button type="button" class="secondary btn-ignore-record" data-job="${escapeHtml(updId)}" data-row="${escapeHtml(String(csvRow))}" title="${escapeHtml(actionTitle)}">
                ${escapeHtml(t("btn_ignore_row"))}
              </button>
            `;
          return `
            <tr class="${ignored ? "analysis-row-ignored" : ""}">
              <td class="col-idx col-num" title="${escapeHtml(`csv_row_index=${String(csvRow || "—")}`)}"><code>${escapeHtml(String(i + 1))}</code></td>
              <td class="col-rt"><code>${escapeHtml(rt || "—")}</code></td>
              <td class="muted col-metric" title="${escapeHtml(metric || "")}"><code>${escapeHtml(metricLabel || "—")}</code></td>
              <td class="col-pred" title="${escapeHtml(pred)}"><code>${escapeHtml(pred)}</code></td>
              <td class="col-act" title="${escapeHtml(act)}"><code>${escapeHtml(act)}</code></td>
              <td class="col-abs"><code>${escapeHtml(abs)}</code></td>
              <td class="col-rel col-num"><code>${escapeHtml(rel)}</code></td>
              <td class="col-reco" title="${escapeHtml(recoId)}"><code>${escapeHtml(shortId(recoId))}</code></td>
              <td class="col-upd" title="${escapeHtml(updId)}"><code>${escapeHtml(shortId(updId))}</code></td>
              <td class="col-actions">${actionHtml}</td>
            </tr>
          `;
        })
        .join("");

      return `
        <details class="details" ${gi === 0 ? "open" : ""}>
          <summary>${escapeHtml(summary)}</summary>
          ${hideRoundHtml}
          <div class="table-wrap">
            <table class="table analysis-records-table">
              <colgroup>
                <col class="col-idx" />
                <col class="col-rt" />
                <col class="col-metric" />
                <col class="col-pred" />
                <col class="col-act" />
                <col class="col-abs" />
                <col class="col-rel" />
                <col class="col-reco" />
                <col class="col-upd" />
                <col class="col-actions" />
              </colgroup>
              <thead>
                ${statsRow}
                <tr>
                  <th class="col-idx col-num">${headIdx}</th>
                  <th class="col-rt">${headRt}</th>
                  <th class="col-metric">${headMetric}</th>
                  <th class="col-pred">${headPred}</th>
                  <th class="col-act">${headAct}</th>
                  <th class="col-abs">${headAbs}</th>
                  <th class="col-rel col-num">${headRel}</th>
                  <th class="col-reco">${headReco}</th>
                  <th class="col-upd">${headUpd}</th>
                  <th class="col-actions">${headActions}</th>
                </tr>
              </thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
        </details>
      `;
    })
    .join("");

  return `
    <div class="row"><b>${escapeHtml(boxTitle)}</b></div>
    <div class="hint muted">${escapeHtml(hint)}</div>
    <div class="hint muted">${escapeHtml(t("analysis_ignore_tip"))}</div>
    <div class="row">
      <a class="secondary" href="#experience">${escapeHtml(t("btn_go_experience_rollback"))}</a>
      <a class="secondary" href="#feedback">${escapeHtml(t("btn_go_feedback_resubmit"))}</a>
    </div>
    <div class="stack">${blocks}</div>
  `;
}

function renderAnalysisControls() {
  const kindSel = document.getElementById("analysis-agg-kind");
  const stepSel = document.getElementById("analysis-agg-step");
  const stepWrap = document.getElementById("analysis-agg-step-wrap");
  const hint = document.getElementById("analysis-agg-hint");
  if (!kindSel || !stepSel || !stepWrap || !hint) return;

  const kind = getAnalysisAggKind();
  const step = getAnalysisAggStep();

  const kindOpts = [
    { v: "records_bucket", label: t("analysis_agg_kind_records_bucket") },
    { v: "records_cumulative", label: t("analysis_agg_kind_records_cumulative") },
    { v: "rounds", label: t("analysis_agg_kind_rounds") },
  ];
  kindSel.innerHTML = kindOpts.map((o) => `<option value="${o.v}">${escapeHtml(o.label)}</option>`).join("");
  kindSel.value = kindOpts.some((o) => o.v === kind) ? kind : "records_bucket";

  const steps = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 19, 20];
  const want = clampInt(step, 1, 200);
  const all = steps.includes(want) ? steps : [...steps, want].sort((a, b) => a - b);
  stepSel.innerHTML = all.map((n) => `<option value="${n}">${n}</option>`).join("");
  stepSel.value = String(want);

  const showStep = kindSel.value !== "rounds";
  stepWrap.classList.toggle("hidden", !showStep);
  hint.textContent = analysisAggHint(kindSel.value, want);
}

function renderAnalysisFromCache() {
  const chart = document.getElementById("analysis-chart");
  const roundsBox = document.getElementById("analysis-rounds");
  if (!chart) return;
  if (!analysisCache) return;

  renderAnalysisControls();

  const kind = document.getElementById("analysis-agg-kind")?.value || getAnalysisAggKind();
  const step = clampInt(document.getElementById("analysis-agg-step")?.value || getAnalysisAggStep(), 1, 200);

  const pts = buildAnalysisPoints({ rounds: analysisCache.rounds || [], records: analysisCache.records || [] }, { kind, step });
  const title = getLang() === "zh" ? "相对误差趋势（点 + 折线）" : "Relative error trend (dots + line)";
  const subtitle =
    getLang() === "zh"
      ? "提示：越低越好；误差棒为 ±1σ（同一桶/同一回合内的离散程度）。鼠标悬停点可查看区间与均值。"
      : "Tip: lower is better; error bars are ±1σ (spread within a bucket/round). Hover points for details.";
  const xLabel =
    kind === "rounds"
      ? getLang() === "zh"
        ? "回合"
        : "Round"
      : kind === "records_cumulative"
        ? getLang() === "zh"
          ? "累计记录区间"
          : "Cumulative record range"
        : getLang() === "zh"
          ? "记录区间"
          : "Record range";
  const yLabel = getLang() === "zh" ? "相对误差（均值±1σ）" : "Relative error (mean ± 1σ)";
  const chartHtml = renderRelErrorLineChart(pts, { title, subtitle, xLabel, yLabel });
  if (chartHtml) {
    chart.innerHTML = chartHtml;
    chart.classList.remove("hidden");
  } else {
    chart.innerHTML = "";
    chart.classList.add("hidden");
  }

  if (roundsBox) {
    const html = renderAnalysisRecordsTable(
      { rounds: analysisCache.rounds || [], records: analysisCache.records || [] },
      { kind, step, points: pts }
    );
    if (html) {
      roundsBox.innerHTML = html;
      roundsBox.classList.remove("hidden");

      if (kind === "rounds") {
        roundsBox.querySelectorAll(".btn-hide-round").forEach((btn) => {
          btn.addEventListener("click", async () => {
            const jobId = btn.getAttribute("data-job") || "";
            if (!jobId) return;
            const ok = confirm(
              getLang() === "zh"
                ? `确定要删除/隐藏该回合吗？\n\nupdate_job_id=${jobId}\n\n这不会删除经验库文件本身，但会把这一回合从效果评估里移除。`
                : `Hide/delete this feedback round?\n\nupdate_job_id=${jobId}\n\nThis will remove it from Analytics (it does not delete the experience pack file itself).`
            );
            if (!ok) return;
            try {
              await apiJson(`/api/jobs/${encodeURIComponent(jobId)}/hide`, { method: "POST", body: JSON.stringify({}) });
              await refreshAnalysis();
            } catch (e) {
              alert(String(e.message || e));
            }
          });
        });
      }

      roundsBox.querySelectorAll(".btn-ignore-record").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const jobId = btn.getAttribute("data-job") || "";
          const row = Number(btn.getAttribute("data-row") || "");
          if (!jobId || !Number.isFinite(row) || row <= 0) return;
          const ok = confirm(
            getLang() === "zh"
              ? `确定要忽略此条记录吗？\n\nupdate_job_id=${jobId}\ncsv_row_index=${row}\n\n说明：忽略只影响效果评估统计，不会回滚经验库。若经验库已被错误数据污染，请到「经验库」回滚到未污染版本，然后重新提交反馈。`
              : `Ignore this record?\n\nupdate_job_id=${jobId}\ncsv_row_index=${row}\n\nNote: this only affects Analytics statistics; it does not roll back the experience pack. If the pack was contaminated by wrong data, roll back to a previous version and resubmit feedback.`
          );
          if (!ok) return;
          try {
            await apiJson(`/api/jobs/${encodeURIComponent(jobId)}/analytics_ignore`, {
              method: "POST",
              body: JSON.stringify({ csv_row_index: row }),
            });
            await refreshAnalysis();
          } catch (e) {
            alert(String(e.message || e));
          }
        });
      });

      roundsBox.querySelectorAll(".btn-unignore-record").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const jobId = btn.getAttribute("data-job") || "";
          const row = Number(btn.getAttribute("data-row") || "");
          if (!jobId || !Number.isFinite(row) || row <= 0) return;
          const ok = confirm(
            getLang() === "zh"
              ? `确定要恢复此条记录吗？\n\nupdate_job_id=${jobId}\ncsv_row_index=${row}`
              : `Restore this record?\n\nupdate_job_id=${jobId}\ncsv_row_index=${row}`
          );
          if (!ok) return;
          try {
            await apiJson(`/api/jobs/${encodeURIComponent(jobId)}/analytics_unignore`, {
              method: "POST",
              body: JSON.stringify({ csv_row_index: row }),
            });
            await refreshAnalysis();
          } catch (e) {
            alert(String(e.message || e));
          }
        });
      });
    } else {
      roundsBox.innerHTML = "";
      roundsBox.classList.add("hidden");
    }
  }
}

async function refreshAnalysis() {
  const box = document.getElementById("analysis-summary");
  const chart = document.getElementById("analysis-chart");
  const roundsBox = document.getElementById("analysis-rounds");
  const rawBox = document.getElementById("analysis-records");
  if (!box || !chart || !roundsBox || !rawBox) return;

  box.textContent = t("loading");
  chart.classList.add("hidden");
  roundsBox.classList.add("hidden");
  rawBox.textContent = t("empty");

  try {
    const data = await apiJson("/api/analytics?limit_rounds=80&limit_records=5000", { method: "GET", headers: {} });
    const overall = data.overall || {};
    const rounds = data.rounds || [];
    const records = data.records || [];
    analysisCache = { overall, rounds, records };

    const rel = overall.mean_rel_error != null ? Number(overall.mean_rel_error).toFixed(3) : "—";
    const nRecords = overall.total_records != null ? Number(overall.total_records) : 0;
    const nIgnored = overall.total_records_ignored != null ? Number(overall.total_records_ignored) : 0;
    const ignoredLine =
      nIgnored > 0
        ? getLang() === "zh"
          ? ` · 已忽略: <code>${escapeHtml(String(nIgnored))}</code>`
          : ` · ignored: <code>${escapeHtml(String(nIgnored))}</code>`
        : "";
    const hint1 =
      getLang() === "zh"
        ? "相对误差越低越好（0.2≈20%，0.5≈50%，1.0≈100%）。误差棒为 ±1σ，用来表示同一组/同一回合内的离散程度。"
        : "Lower relative error is better (0.2≈20%, 0.5≈50%, 1.0≈100%). Error bars are ±1σ, showing spread within the same group/round.";
    const hint2 =
      getLang() === "zh"
        ? "相对误差计算：rel_error = |pred - actual| / (|actual| + floor)。其中 floor 用于避免 actual 接近 0 时爆炸（V 与 0–1 分数类指标默认 floor=0.05）。"
        : "Definition: rel_error = |pred - actual| / (|actual| + floor). We add a small floor to avoid blow-ups when actual≈0 (floor=0.05 for V and 0–1 fraction metrics).";
    box.innerHTML = `
      ${pill("completed")}
      <b>${escapeHtml(getLang() === "zh" ? "总体统计" : "Overall")}</b><br/>
      ${escapeHtml(getLang() === "zh" ? "回合数" : "Rounds")}: <code>${escapeHtml(String(overall.total_rounds ?? 0))}</code> ·
      ${escapeHtml(getLang() === "zh" ? "记录数" : "Records")}: <code>${escapeHtml(String(nRecords))}</code>${ignoredLine}<br/>
      ${escapeHtml(getLang() === "zh" ? "平均相对误差(越低越好)" : "Mean relative error (lower is better)")}: <code>${escapeHtml(rel)}</code><br/>
      <span class="muted">${escapeHtml(hint1)}</span><br/>
      <span class="muted">${escapeHtml(hint2)}</span>
    `;

    renderAnalysisControls();
    renderAnalysisFromCache();

    rawBox.textContent = JSON.stringify({ overall, rounds, records }, null, 2);
  } catch (e) {
    box.innerHTML = `${pill("failed")} ${escapeHtml(String(e.message || e))}`;
  }
}

function init() {
  // Language + theme
  document.getElementById("lang-select")?.addEventListener("change", (e) => setLang(e.target.value));
  document.getElementById("theme-toggle")?.addEventListener("click", () => {
    const next = getTheme() === "dark" ? "light" : "dark";
    setTheme(next);
  });

  // Route
  window.addEventListener("hashchange", () => setActiveRoute(currentRoute()));
  setActiveRoute(currentRoute());

  // History (recommendation jobs)
  document.getElementById("btn-refresh-history")?.addEventListener("click", async () => {
    await refreshHistoryRecommendations();
  });
  document.getElementById("history-show-deleted")?.addEventListener("change", async () => {
    await refreshHistoryRecommendations();
  });
  document.getElementById("history-search")?.addEventListener("keydown", async (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      try {
        await refreshHistoryRecommendations();
      } catch {}
    }
  });

  // Manual feedback: multi-recommendation blocks
  document.getElementById("btn-reco-refresh")?.addEventListener("click", async () => {
    try {
      await refreshRecoList();
    } catch (e) {
      alert(String(e.message || e));
    }
  });
  document.getElementById("reco-search")?.addEventListener("keydown", async (e) => {
    if (e.key === "Escape") {
      hideRecoSuggestions();
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      try {
        await refreshRecoList();
      } catch {}
    }
  });
  document.getElementById("reco-search")?.addEventListener("input", () => {
    scheduleRecoSuggestionsRefresh();
  });
  document.getElementById("reco-search")?.addEventListener("focus", () => {
    scheduleRecoSuggestionsRefresh();
  });
  document.addEventListener("click", (e) => {
    const box = recoSuggestionsBox();
    const input = document.getElementById("reco-search");
    const target = e?.target || null;
    if (!box || box.classList.contains("hidden")) return;
    if (input && target === input) return;
    try {
      if (box.contains(target)) return;
    } catch {}
    hideRecoSuggestions();
  });
  document.getElementById("btn-add-reco-group")?.addEventListener("click", () => {
    ensureManualGroupsInitialized();
    const g = createManualGroupCard();
    if (g) {
      renderRecoOptionsForAllManualGroups();
      setManualGroupActive(g.groupId);
      g.el?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    }
  });
  ensureManualGroupsInitialized();
  refreshRecoList().catch(() => {});

  // Recommend: initialize the repeatable material input list (1-10 entries).
  const recommendCount = document.getElementById("recommend-material-count");
  recommendCount?.addEventListener("change", (ev) => {
    renderRecommendMaterialInputs(ev.target.value);
  });
  renderRecommendMaterialInputs(recommendCount?.value || 1);

  // Unified experience build entry backed by the material-property GRPO pipeline.
  document.getElementById("experience-build-mode")?.addEventListener("change", setExperienceBuildDefaultsFromMode);
  setExperienceBuildDefaultsFromMode();
  const experienceBuildStatus = document.getElementById("experience-build-status");
  const experienceBuildRunning = document.getElementById("experience-build-running");
  const experienceBuildRunningText = document.getElementById("experience-build-running-text");
  const experienceBuildProgressFill = document.getElementById("experience-build-progress-fill");
  const experienceBuildProgressHint = document.getElementById("experience-build-progress-hint");
  const experienceBuildResult = document.getElementById("experience-build-result");
  const experienceBuildLog = document.getElementById("experience-build-log");
  const btnExperienceBuildLog = document.getElementById("btn-experience-build-log");
  const btnExperienceBuildStop = document.getElementById("btn-experience-build-stop");

  document.getElementById("form-experience-build")?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    experienceBuildResult?.classList.add("hidden");
    if (btnExperienceBuildLog) btnExperienceBuildLog.disabled = true;
    if (btnExperienceBuildStop) {
      btnExperienceBuildStop.disabled = true;
      btnExperienceBuildStop.onclick = null;
    }
    if (experienceBuildProgressFill) experienceBuildProgressFill.style.width = "0%";
    if (experienceBuildProgressHint) experienceBuildProgressHint.textContent = "";
    if (experienceBuildLog) experienceBuildLog.textContent = t("empty");

    const uiMode = String(document.getElementById("experience-build-mode")?.value || "prepare_only");
    const prepareOnly = uiMode === "prepare_only";
    const expName = String(document.getElementById("experience-build-exp-name")?.value || "").trim();
    const truncate = Number(document.getElementById("experience-build-truncate")?.value || 11291);
    const batchSize = Number(document.getElementById("experience-build-batch")?.value || 50);
    const grpoN = Number(document.getElementById("experience-build-grpo-n")?.value || 3);
    const concurrency = Number(document.getElementById("experience-build-concurrency")?.value || 1);
    const rag = Boolean(document.getElementById("experience-build-rag")?.checked);
    const resume = Boolean(document.getElementById("experience-build-resume")?.checked);

    const body = {
      mode: prepareOnly ? "prepare_only" : "grpo",
      run_mode: prepareOnly ? "prepare_only" : resume ? "resume" : "fresh",
      exp_name: expName || undefined,
      truncate,
      batch_size: batchSize,
      grpo_n: grpoN,
      rollout_concurrency: concurrency,
      epochs: 1,
      mad_enable_rag: rag,
    };

    try {
      experienceBuildStatus.innerHTML = `${pill("running")} ${escapeHtml(t("submitting"))}`;
      syncJobRunningIndicator(experienceBuildRunning, "running", experienceBuildRunningText, "");

      const res = await apiJson("/api/experience/material-property/run", {
        method: "POST",
        body: JSON.stringify(body),
      });
      const jobId = res.job_id;

      if (btnExperienceBuildLog) {
        btnExperienceBuildLog.disabled = false;
        btnExperienceBuildLog.onclick = async () => {
          if (experienceBuildLog) experienceBuildLog.textContent = await apiText(`/api/jobs/${jobId}/log`);
        };
      }
      if (btnExperienceBuildStop) {
        btnExperienceBuildStop.disabled = false;
        btnExperienceBuildStop.onclick = async () => {
          try {
            experienceBuildStatus.innerHTML = `${pill("cancelling")} ${escapeHtml(getLang() === "zh" ? "正在停止…" : "Cancelling…")}`;
            syncJobRunningIndicator(experienceBuildRunning, "cancelling");
            btnExperienceBuildStop.disabled = true;
            await apiJson(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST", body: JSON.stringify({}) });
          } catch (e) {
            experienceBuildStatus.innerHTML = `${pill("failed")} ${escapeHtml(String(e.message || e))}`;
          }
        };
      }

      const finalJob = await pollJob(
        jobId,
        (j, logText) => {
          syncJobRunningIndicator(experienceBuildRunning, j.status);
          const started = j.started_at_utc ? fmtBeijing(j.started_at_utc) : "—";
          const finished = j.finished_at_utc ? fmtBeijing(j.finished_at_utc) : null;
          experienceBuildStatus.innerHTML = `${pill(j.status)} ${escapeHtml(t("job_id"))}=<code>${escapeHtml(j.id)}</code> · ${escapeHtml(t("started_at"))}: <code>${escapeHtml(started)}</code>${
            finished ? ` · ${escapeHtml(t("finished_at"))}: <code>${escapeHtml(finished)}</code>` : ""
          } ${j.error ? `· <span class="muted">${escapeHtml(j.error)}</span>` : ""}`;
          if (logText) {
            if (experienceBuildLog) experienceBuildLog.textContent = logText || t("empty");
            const step = parseStepFromLog(logText);
            if (step && step.total && experienceBuildProgressFill && experienceBuildProgressHint) {
              const pct = Math.max(0, Math.min(100, Math.round((step.cur / step.total) * 100)));
              experienceBuildProgressFill.style.width = `${pct}%`;
              experienceBuildProgressHint.textContent = `[${step.cur}/${step.total}] ${step.title || ""}`;
            }
            const lines = logText.trim().split("\n");
            const last = lines.length ? lines[lines.length - 1] : "";
            if (experienceBuildRunningText) experienceBuildRunningText.textContent = last ? last.slice(0, 220) : "";
          }
        },
        { intervalMs: 2500, maxMs: 8 * 60 * 60 * 1000, alsoLog: true }
      );

      syncJobRunningIndicator(experienceBuildRunning, finalJob.status);
      if (finalJob.status !== "completed") return;
      const resultPayload = await apiJson(`/api/jobs/${jobId}/result`, { method: "GET", headers: {} });
      experienceBuildResult.innerHTML = renderExperienceBuildResult(jobId, resultPayload);
      experienceBuildResult.classList.remove("hidden");
    } catch (e) {
      syncJobRunningIndicator(experienceBuildRunning, "failed");
      experienceBuildStatus.innerHTML = `${pill("failed")} ${escapeHtml(String(e.message || e))}`;
    } finally {
      syncJobRunningIndicator(experienceBuildRunning, null);
      if (btnExperienceBuildStop) {
        btnExperienceBuildStop.disabled = true;
        btnExperienceBuildStop.onclick = null;
      }
      await refreshExperienceMeta();
      await renderExperienceHistory();
      await renderExperienceCurrent();
    }
  });

  // Experience meta/history
  document.getElementById("btn-refresh-meta")?.addEventListener("click", async () => {
    await refreshExperienceMeta();
    await renderExperienceHistory();
  });
  document.getElementById("experience-search")?.addEventListener("input", () => {
    setExperiencePage(1);
    renderExperienceCurrentFromCache();
  });
  document.getElementById("btn-experience-search-clear")?.addEventListener("click", () => {
    const input = document.getElementById("experience-search");
    if (input) input.value = "";
    setExperiencePage(1);
    renderExperienceCurrentFromCache();
  });

  // Analysis
  document.getElementById("btn-refresh-analysis")?.addEventListener("click", async () => {
    await refreshAnalysis();
  });
  document.getElementById("analysis-agg-kind")?.addEventListener("change", (e) => {
    setAnalysisAggKind(e.target.value);
    renderAnalysisControls();
    renderAnalysisFromCache();
  });
  document.getElementById("analysis-agg-step")?.addEventListener("change", (e) => {
    setAnalysisAggStep(e.target.value);
    renderAnalysisControls();
    renderAnalysisFromCache();
  });

  // Recommend form
  const recommendStatus = document.getElementById("recommend-status");
  const recommendRunning = document.getElementById("recommend-running");
  const recommendRunningText = document.getElementById("recommend-running-text");
  const recommendResult = document.getElementById("recommend-result");
  const recommendLog = document.getElementById("recommend-log");
  const btnRecommendLog = document.getElementById("btn-recommend-log");
  const btnRecommendStop = document.getElementById("btn-recommend-stop");

  document.getElementById("form-recommend")?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    recommendResult?.classList.add("hidden");
    const btnRecommend = document.getElementById("btn-recommend");
    if (btnRecommend) btnRecommend.disabled = true;
    if (btnRecommendLog) btnRecommendLog.disabled = true;
    if (btnRecommendStop) {
      btnRecommendStop.disabled = true;
      btnRecommendStop.onclick = null;
    }

    const cards = [...document.querySelectorAll(".recommend-material-card")];
    const materialInputs = cards.map((card) => readRecommendMaterialCard(card));
    const missingIndex = materialInputs.findIndex((item) => !String(item.material_name || "").trim());
    if (missingIndex >= 0) {
      recommendStatus.innerHTML = `${pill("failed")} ${escapeHtml(getLang() === "zh" ? "材料名称为必填项。" : "Material name is required.")}`;
      const missingInput = cards[missingIndex]?.querySelector('[data-recommend-field="material_name"]');
      missingInput?.focus();
      if (btnRecommend) btnRecommend.disabled = false;
      return;
    }
    const invalidSerialIndex = materialInputs.findIndex((item) => normalizeMaterialSerial(item.material_serial_no) == null);
    if (invalidSerialIndex >= 0) {
      recommendStatus.innerHTML = `${pill("failed")} ${escapeHtml(
        getLang() === "zh" ? "材料序号必须是大于等于 1 的正整数。" : "Material serial number must be a positive integer."
      )}`;
      cards[invalidSerialIndex]?.querySelector('[data-recommend-field="material_serial_no"]')?.focus();
      if (btnRecommend) btnRecommend.disabled = false;
      return;
    }
    const readText = (id) => document.getElementById(id)?.value?.trim() || "";
    const selectedTask = readText("recommend-task-type") || "__all__";
    const selectedTasks = selectedTask === "__all__" ? REACTION_TYPES.map((item) => item.key) : [selectedTask];
    const topk = Math.max(1, Math.min(REACTION_TYPES.length, Number(document.getElementById("recommend-topk").value || 2)));
    const parallel = Math.max(1, Math.min(REACTION_TYPES.length, Number(document.getElementById("recommend-parallel").value || 1)));
    // Always save full per-task debate traces for later feedback alignment.
    const saveEach = true;

    recommendStatus.innerHTML = `${pill("running")} ${escapeHtml(t("recommend_batch_submitting"))}`;
    syncJobRunningIndicator(recommendRunning, "running", recommendRunningText, "");
    recommendLog.textContent = t("empty");
    try {
      const entries = materialInputs.map((materialInput, index) => ({
        index,
        materialInput,
        jobId: null,
        job: null,
        logText: "",
        resultPayload: null,
        error: null,
      }));

      await Promise.all(
        entries.map(async (entry) => {
          try {
            const body = {
              material_input: entry.materialInput,
              top_k_properties: topk,
              task_types: selectedTasks,
              max_parallel_properties: parallel,
              save_each_task: saveEach,
            };
            const res = await apiJson("/api/recommendations/rank", { method: "POST", body: JSON.stringify(body) });
            entry.jobId = String(res.job_id || "").trim() || null;
            entry.job = { id: entry.jobId, status: entry.jobId ? "queued" : "failed" };
            if (!entry.jobId) entry.error = getLang() === "zh" ? "后端没有返回任务 ID。" : "Backend did not return a job ID.";
            updateRecommendBatchLog(entries);
            if (entry.jobId) {
              try {
                entry.logText = await apiText(`/api/jobs/${encodeURIComponent(entry.jobId)}/log`);
              } catch {
                entry.logText = "";
              }
              updateRecommendBatchLog(entries);
            }
          } catch (error) {
            entry.job = { status: "failed" };
            entry.error = String(error?.message || error);
          }
        })
      );

      const acceptedEntries = entries.filter((entry) => entry.jobId);
      const renderBatchStatus = () => {
        const terminalStatuses = new Set(["completed", "failed", "cancelled"]);
        const done = entries.filter((entry) => terminalStatuses.has(String(entry.job?.status || ""))).length;
        const active = entries.some((entry) => isActiveJobStatus(entry.job?.status));
        const failed = entries.some((entry) => ["failed", "cancelled"].includes(String(entry.job?.status || "")));
        const status = active ? "running" : failed ? "failed" : done >= entries.length ? "completed" : "queued";
        const startedMs = entries
          .map((entry) => Date.parse(String(entry.job?.started_at_utc || "")))
          .filter((value) => Number.isFinite(value))
          .sort((a, b) => a - b)[0];
        const finishedMs = entries
          .map((entry) => Date.parse(String(entry.job?.finished_at_utc || "")))
          .filter((value) => Number.isFinite(value))
          .sort((a, b) => b - a)[0];
        const timingJob = {
          started_at_utc: Number.isFinite(startedMs) ? new Date(startedMs).toISOString() : null,
          finished_at_utc: !active && Number.isFinite(finishedMs) ? new Date(finishedMs).toISOString() : null,
        };
        const started = timingJob.started_at_utc ? fmtBeijing(timingJob.started_at_utc) : "—";
        const finished = timingJob.finished_at_utc ? fmtBeijing(timingJob.finished_at_utc) : null;
        const duration = fmtDurationSeconds(durationSecondsForJob(timingJob));
        const durationLabel = finished ? t("duration") : t("elapsed");
        const timing = Number.isFinite(startedMs)
          ? ` · ${escapeHtml(t("started_at"))}: <code>${escapeHtml(started)}</code>${finished ? ` · ${escapeHtml(t("finished_at"))}: <code>${escapeHtml(finished)}</code>` : ""} · ${escapeHtml(durationLabel)}: <code>${escapeHtml(duration)}</code>`
          : "";
        recommendStatus.innerHTML = `${pill(status)} ${escapeHtml(recommendBatchProgressText(done, entries.length))}${timing}`;
        recommendRunningText.textContent = recommendBatchProgressText(done, entries.length);
        syncJobRunningIndicator(recommendRunning, active ? "running" : status);
      };

      if (!acceptedEntries.length) {
        recommendStatus.innerHTML = `${pill("failed")} ${escapeHtml(t("recommend_batch_empty"))}`;
        recommendResult.innerHTML = renderRecommendBatchResult(entries, entries.length);
        recommendResult.classList.remove("hidden");
        return;
      }

      renderBatchStatus();
      if (btnRecommendLog) btnRecommendLog.disabled = false;
      if (btnRecommendLog) {
        btnRecommendLog.onclick = async () => {
          await Promise.all(
            entries
              .filter((entry) => entry.jobId)
              .map(async (entry) => {
                try {
                  entry.logText = await apiText(`/api/jobs/${encodeURIComponent(entry.jobId)}/log`);
                } catch (error) {
                  entry.logText = String(error?.message || error);
                }
              })
          );
          updateRecommendBatchLog(entries);
        };
      }
      if (btnRecommendStop) {
        btnRecommendStop.disabled = false;
        btnRecommendStop.onclick = async () => {
          try {
            recommendStatus.innerHTML = `${pill("cancelling")} ${escapeHtml(getLang() === "zh" ? "正在停止…" : "Cancelling…")}`;
            syncJobRunningIndicator(recommendRunning, "cancelling");
            btnRecommendStop.disabled = true;
            await Promise.allSettled(
              entries
                .filter((entry) => entry.jobId && isActiveJobStatus(entry.job?.status))
                .map((entry) => apiJson(`/api/jobs/${encodeURIComponent(entry.jobId)}/cancel`, { method: "POST", body: JSON.stringify({}) }))
            );
          } catch (e) {
            recommendStatus.innerHTML = `${pill("failed")} ${escapeHtml(String(e.message || e))}`;
          }
        };
      }

      await Promise.all(
        acceptedEntries.map(async (entry) => {
          try {
            entry.job = await pollJob(
              entry.jobId,
              (job, logText) => {
                entry.job = job;
                if (logText !== null && logText !== undefined) entry.logText = String(logText);
                updateRecommendBatchLog(entries);
                renderBatchStatus();
              },
              { intervalMs: 2500, maxMs: 2 * 60 * 60 * 1000, alsoLog: true }
            );
          } catch (error) {
            entry.job = { id: entry.jobId, status: "failed", error: String(error?.message || error) };
            entry.error = String(error?.message || error);
          }
        })
      );

      await Promise.all(
        acceptedEntries
          .filter((entry) => entry.job?.status === "completed")
          .map(async (entry) => {
            try {
              entry.resultPayload = await apiJson(`/api/jobs/${encodeURIComponent(entry.jobId)}/result`, { method: "GET", headers: {} });
            } catch (error) {
              entry.job = { ...entry.job, status: "failed", error: String(error?.message || error) };
              entry.error = String(error?.message || error);
            }
          })
      );

      renderBatchStatus();
      recommendResult.innerHTML = renderRecommendBatchResult(entries, entries.length);
      wireHistoryRecoResultBox(recommendResult, acceptedEntries[0]?.jobId || "");
      recommendResult.classList.remove("hidden");
    } catch (e) {
      syncJobRunningIndicator(recommendRunning, "failed");
      recommendStatus.innerHTML = `${pill("failed")} ${escapeHtml(String(e.message || e))}`;
    } finally {
      syncJobRunningIndicator(recommendRunning, null);
      if (btnRecommend) btnRecommend.disabled = false;
      if (btnRecommendStop) {
        btnRecommendStop.disabled = true;
        btnRecommendStop.onclick = null;
      }
      await refreshExperienceMeta();
      await renderExperienceHistory();
    }
  });

  // Update form
  const updateStatus = document.getElementById("update-status");
  const updateRunning = document.getElementById("update-running");
  const updateRunningText = document.getElementById("update-running-text");
  const updateProgressFill = document.getElementById("update-progress-fill");
  const updateProgressHint = document.getElementById("update-progress-hint");
  const updateResult = document.getElementById("update-result");
  const updateLog = document.getElementById("update-log");
  const btnUpdateLog = document.getElementById("btn-update-log");
  const btnUpdateStop = document.getElementById("btn-update-stop");

  document.getElementById("form-update")?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    updateResult?.classList.add("hidden");
    btnUpdateLog.disabled = true;
    if (btnUpdateStop) {
      btnUpdateStop.disabled = true;
      btnUpdateStop.onclick = null;
    }
    updateProgressFill.style.width = "0%";
    updateProgressHint.textContent = "";
    updateLog.textContent = t("empty");

    const tag = document.getElementById("update-tag").value.trim() || "lab";
    const grpoN = String(document.getElementById("update-n").value || 3);
    const rolloutC = String(document.getElementById("update-c").value || 4);
    const epochs = String(document.getElementById("update-e").value || 1);

    const runOneUpdateJob = async (fd, { queuePrefix = "" } = {}) => {
      updateProgressFill.style.width = "0%";
      updateProgressHint.textContent = "";

      updateStatus.innerHTML = `${pill("running")} ${
        queuePrefix ? `<span class="muted">${escapeHtml(queuePrefix)} ·</span> ` : ""
      }${escapeHtml(t("uploading_starting"))}`;
      syncJobRunningIndicator(updateRunning, "running", updateRunningText, "");

      const resp = await fetch("/api/experience/update", { method: "POST", body: fd });
      const txt = await resp.text();
      if (!resp.ok) throw new Error(txt || `HTTP ${resp.status}`);
      const res = JSON.parse(txt);
      const jobId = res.job_id;

      btnUpdateLog.disabled = false;
      btnUpdateLog.onclick = async () => {
        updateLog.textContent = await apiText(`/api/jobs/${jobId}/log`);
      };
      if (btnUpdateStop) {
        btnUpdateStop.disabled = false;
        btnUpdateStop.onclick = async () => {
          try {
            updateStatus.innerHTML = `${pill("cancelling")} ${escapeHtml(getLang() === "zh" ? "正在停止…" : "Cancelling…")}`;
            syncJobRunningIndicator(updateRunning, "cancelling");
            btnUpdateStop.disabled = true;
            await apiJson(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST", body: JSON.stringify({}) });
          } catch (e) {
            updateStatus.innerHTML = `${pill("failed")} ${escapeHtml(String(e.message || e))}`;
          }
        };
      }

      const finalJob = await pollJob(
        jobId,
        (j, logText) => {
          syncJobRunningIndicator(updateRunning, j.status);
          const started = j.started_at_utc ? fmtBeijing(j.started_at_utc) : "—";
          const finished = j.finished_at_utc ? fmtBeijing(j.finished_at_utc) : null;
          updateStatus.innerHTML = `${pill(j.status)} ${
            queuePrefix ? `<span class="muted">${escapeHtml(queuePrefix)} ·</span> ` : ""
          }${escapeHtml(t("job_id"))}=<code>${escapeHtml(j.id)}</code> · ${escapeHtml(t("started_at"))}: <code>${escapeHtml(started)}</code>${
            finished ? ` · ${escapeHtml(t("finished_at"))}: <code>${escapeHtml(finished)}</code>` : ""
          } ${j.error ? `· <span class="muted">${escapeHtml(j.error)}</span>` : ""}`;
          if (logText) {
            updateLog.textContent = logText || t("empty");
            const step = parseStepFromLog(logText);
            if (step && step.total) {
              const pct = Math.max(0, Math.min(100, Math.round((step.cur / step.total) * 100)));
              updateProgressFill.style.width = `${pct}%`;
              updateProgressHint.textContent = `[${step.cur}/${step.total}] ${step.title || ""}`;
            }
            const lines = logText.trim().split("\n");
            const last = lines.length ? lines[lines.length - 1] : "";
            updateRunningText.textContent = last ? last.slice(0, 220) : "";
          }
        },
        { intervalMs: 2500, maxMs: 6 * 60 * 60 * 1000, alsoLog: true }
      );

      syncJobRunningIndicator(updateRunning, finalJob.status);

      let resultPayload = null;
      if (finalJob.status === "completed") {
        try {
          resultPayload = await apiJson(`/api/jobs/${jobId}/result`, { method: "GET", headers: {} });
        } catch {
          resultPayload = null;
        }
      }
      return { jobId, finalJob, resultPayload };
    };

    try {
      // Manual mode: allow selecting multiple recommendation blocks to submit.
      const sel = collectManualGroupsForSubmit();

      const plans = [];
      for (const g of sel.groups) {
        const est = estimateManualGroupUpdateSize(g);
        if (est.numRows <= 0) {
          updateStatus.innerHTML = `${pill("failed")} ${escapeHtml(t("manual_no_rows"))}`;
          syncJobRunningIndicator(updateRunning, "failed");
          return;
        }
        let csv = "";
        try {
          csv = buildManualCsvForGroup(g, { includeHeader: plans.length === 0 });
        } catch (e) {
          updateStatus.innerHTML = `${pill("failed")} ${escapeHtml(String(e.message || e))}`;
          syncJobRunningIndicator(updateRunning, "failed");
          return;
        }
        const materialName = String(readManualGroupMaterialInputFromDom(g).material_name || "").trim();
        plans.push({ group: g, csv, materialName, nRows: est.numRows, numSamplesEst: est.numSamplesEst });
      }

      if (!plans.length) {
        updateStatus.innerHTML = `${pill("failed")} ${escapeHtml(getLang() === "zh" ? "没有可提交的反馈块。" : "No blocks to submit.")}`;
        return;
      }

      const recoIds = [];
      const recoSeen = new Set();
      let totalRows = 0;
      let totalSamplesEst = 0;
      let mergedCsv = "";
      for (const p of plans) {
        mergedCsv += p.csv;
        totalRows += p.nRows;
        totalSamplesEst += p.numSamplesEst;
        const rid = String(p.group?.recoJobId || "").trim();
        if (rid && !recoSeen.has(rid)) {
          recoSeen.add(rid);
          recoIds.push(rid);
        }
      }

      const warnSmall = totalSamplesEst > 0 && totalSamplesEst < FIXED_UPDATE_BATCH_SIZE;
      const needConfirm = plans.length > 1 || warnSmall;
      if (needConfirm) {
        const lines = plans.map((p, idx) => {
          const recoId = String(p.group?.recoJobId || "").trim();
          const warn = p.numSamplesEst > 0 && p.numSamplesEst < FIXED_UPDATE_BATCH_SIZE ? " ⚠" : "";
          const source = recoId ? `reco=${recoId}` : getLang() === "zh" ? "直接反馈" : "direct feedback";
          return `${idx + 1}) material=${p.materialName} · ${source} · rows=${p.nRows} · samples≈${p.numSamplesEst}${warn}`;
        });
          const msg =
            getLang() === "zh"
            ? `将提交 ${plans.length} 个反馈块（会合并为 1 个更新任务）：\n\n${lines.join("\n")}\n\n合计：rows=${totalRows}, samples≈${totalSamplesEst}。\n\n提示：标 ⚠ 的块样本数小于 batch_size=${FIXED_UPDATE_BATCH_SIZE}；建议再攒一些数据再更新。\n\n继续吗？`
            : `You are about to submit ${plans.length} block(s) (merged into 1 update job):\n\n${lines.join("\n")}\n\nTotal: rows=${totalRows}, samples≈${totalSamplesEst}.\n\nBlocks marked ⚠ are smaller than batch_size=${FIXED_UPDATE_BATCH_SIZE}; consider accumulating more data.\n\nProceed?`;
        if (!confirm(msg)) {
          updateStatus.innerHTML = `${pill("cancelled")} ${escapeHtml(getLang() === "zh" ? "已取消。" : "Cancelled.")}`;
          return;
        }
      }

      const fd = new FormData();
      const file = new File([mergedCsv], `experimental_records_merged.csv`, { type: "text/csv" });
      fd.append("file", file);
      fd.append("format", "csv");
      // Backward compat: if all rows share the same reco id, also send it as a field.
      if (recoIds.length === 1) fd.append("recommendation_job_id", String(recoIds[0]));
      fd.append("tag", tag);
      fd.append("grpo_n", grpoN);
      fd.append("rollout_concurrency", rolloutC);
      fd.append("epochs", epochs);

      const r = await runOneUpdateJob(fd);
      syncJobRunningIndicator(updateRunning, r.finalJob?.status);

      const st = r.finalJob?.status || "";
      const ds = r.resultPayload?.dataset_name ? `<div>dataset: <code>${escapeHtml(String(r.resultPayload.dataset_name))}</code></div>` : "";
      const ns = r.resultPayload?.num_samples != null ? `<div>num_samples: <code>${escapeHtml(String(r.resultPayload.num_samples))}</code></div>` : "";
      const eid = r.resultPayload?.exp_id ? `<div>exp_id: <code>${escapeHtml(String(r.resultPayload.exp_id))}</code></div>` : "";
      const seedPack = r.resultPayload?.seed_experience_yaml
        ? `<div>${escapeHtml(getLang() === "zh" ? "增量更新起始经验库" : "Seed experience pack")}: <code>${escapeHtml(String(r.resultPayload.seed_experience_yaml))}</code></div>`
        : "";
      const finalPack = r.resultPayload?.active_experience_yaml
        ? `<div>${escapeHtml(getLang() === "zh" ? "当前生效经验库" : "Active experience pack")}: <code>${escapeHtml(String(r.resultPayload.active_experience_yaml))}</code></div>`
        : "";
      const debateTraceCount = Number(r.resultPayload?.debate_trace_files_used || 0);
      const debateTraceLine = `<div>${
        escapeHtml(getLang() === "zh" ? "关联辩论轨迹" : "Linked debate traces")
      }: <code>${escapeHtml(String(debateTraceCount))}</code>${
        debateTraceCount
          ? ` <span class="muted">${escapeHtml(
              getLang() === "zh"
                ? "（已结合预测值与实验真值的偏差，一起蒸馏进经验库）"
                : "(aligned against prediction-vs-ground-truth error and distilled into the experience library)"
            )}</span>`
          : ` <span class="muted">${escapeHtml(
              getLang() === "zh"
                ? "（本次未找到可用轨迹对齐样本，仅使用实验反馈）"
                : "(no trace-aligned feedback examples found; used lab feedback only)"
            )}</span>`
      }</div>`;
      const recoLine = recoIds.length
        ? `<div>reco_ids: <code>${escapeHtml(recoIds.join(", "))}</code></div>`
        : "";
      const actions = `
        <div class="row">
          <a class="secondary" href="/api/jobs/${encodeURIComponent(r.jobId)}/log" target="_blank" rel="noreferrer">${escapeHtml(getLang() === "zh" ? "日志" : "Log")}</a>
          <a class="secondary" href="/api/jobs/${encodeURIComponent(r.jobId)}/result" target="_blank" rel="noreferrer">${escapeHtml(getLang() === "zh" ? "结果" : "Result")}</a>
          <button type="button" class="secondary btn-hide-update-job" data-job="${escapeHtml(r.jobId)}">${escapeHtml(
            getLang() === "zh" ? "从效果评估移除（隐藏本次反馈）" : "Remove from Analytics (hide this feedback)"
          )}</button>
          <a class="secondary" href="#experience">${escapeHtml(getLang() === "zh" ? "回滚经验库版本" : "Rollback experience pack")}</a>
        </div>
        <div class="hint muted">${escapeHtml(
          getLang() === "zh"
            ? "提示：隐藏反馈只会把该回合从“效果评估”中移除，不会自动回滚经验库文件；如已污染经验库，请去“经验库→历史版本”回滚。"
            : "Note: hiding removes this round from Analytics only. It does not roll back the experience pack automatically; use Experience → History to roll back if needed."
        )}</div>
      `;
      updateResult.innerHTML = `
        <div class="row">
          ${pill(st)}
          <b>${escapeHtml(getLang() === "zh" ? "反馈更新任务" : "Feedback update job")}</b>
          <span class="muted">rows=<code>${escapeHtml(String(totalRows))}</code>, samples≈<code>${escapeHtml(String(totalSamplesEst))}</code></span>
        </div>
        <div class="stack">
          <div>${escapeHtml(t("job_id"))}=<code>${escapeHtml(r.jobId)}</code></div>
          ${recoLine}
          ${ds}
          ${ns}
          ${eid}
          ${debateTraceLine}
          ${seedPack}
          ${finalPack}
          ${actions}
        </div>
      `;
      updateResult.classList.remove("hidden");

      updateResult.querySelectorAll("button.btn-hide-update-job").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const jobId = btn.getAttribute("data-job") || "";
          if (!jobId) return;
          const ok = confirm(
            getLang() === "zh"
              ? `确定要隐藏本次反馈吗？\n\nupdate_job_id=${jobId}\n\n这会把该回合从“效果评估”中移除（软删除/可恢复）。\n注意：不会自动回滚经验库文件。`
              : `Hide this feedback update?\n\nupdate_job_id=${jobId}\n\nThis removes it from Analytics (soft-delete/reversible).\nNote: it does not roll back the experience pack automatically.`
          );
          if (!ok) return;
          try {
            await apiJson(`/api/jobs/${encodeURIComponent(jobId)}/hide`, { method: "POST", body: JSON.stringify({}) });
            btn.disabled = true;
            await refreshAnalysis();
          } catch (e) {
            alert(String(e.message || e));
          }
        });
      });
    } catch (e) {
      syncJobRunningIndicator(updateRunning, "failed");
      updateStatus.innerHTML = `${pill("failed")} ${escapeHtml(String(e.message || e))}`;
    } finally {
      syncJobRunningIndicator(updateRunning, null);
      if (btnUpdateStop) {
        btnUpdateStop.disabled = true;
        btnUpdateStop.onclick = null;
      }
      await refreshExperienceMeta();
      await renderExperienceHistory();
      await renderExperienceCurrent();
    }
  });

  // Experience: auto-render
  refreshExperienceMeta();
  renderExperienceHistory();
  renderExperienceCurrent();
  renderAnalysisControls();
  refreshAnalysis();
  refreshHistoryRecommendations().catch(() => {});

  // Init user preferences
  const lang = getLang();
  document.getElementById("lang-select").value = lang;
  applyI18n();
  setTheme(getTheme());
}

init();
