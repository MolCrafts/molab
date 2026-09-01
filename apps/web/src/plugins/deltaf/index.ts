/**
 * ΔF plugin — auto-discovers a Phase-1 quantization run by its
 * `phase1_df_report.json` artifact and adds a "ΔF" tab rendering the
 * force-deviation decomposition (vs the fp32 gold standard) as a molplot bar
 * chart. Pure filename-glob discovery, same mechanism as the metrics plugin.
 */
export { default } from "./plugin";
