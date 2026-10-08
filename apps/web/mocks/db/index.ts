/**
 * In-memory database for MSW mock API responses.
 *
 * This module provides stateful storage for workspace data (projects, experiments, runs, assets, files)
 * with session-scoped persistence. Data survives across requests within a browser tab or test file.
 */

import type {
    ApiProjectResponse,
    ApiExperimentResponse,
    ApiRunResponse,
    ApiAssetResponse,
} from "../../src/app/types";

/**
 * File tree node structure for mock filesystem
 */
export interface FileNode {
    name: string;
    path: string;
    type: "file" | "folder";
    size?: number;
    modified?: string;
    content?: string; // For text files
    children?: FileNode[];
}

/**
 * In-memory database structure
 */
interface MockDatabase {
    projects: Map<string, ApiProjectResponse>;
    experiments: Map<string, ApiExperimentResponse>;
    runs: Map<string, ApiRunResponse>;
    assets: Map<string, ApiAssetResponse>;
    files: Map<string, FileNode>; // path -> node
    runLogs: Map<string, string[]>; // runId -> log lines
}

/**
 * Global database instance
 */
let db: MockDatabase;

/**
 * Helper to generate ISO timestamps relative to a base time
 */
const now = new Date("2025-01-15T12:00:00Z");
const isoAt = (offsetMinutes: number): string => {
    return new Date(now.getTime() + offsetMinutes * 60 * 1000).toISOString();
};

/** Serializable workflow IR used by the page showcase. It deliberately
 * includes typed inputs, parallel links, source snippets and canvas positions
 * so every workflow/run surface has meaningful data to render. */
const workflowIr = (name: string, computeType: string): string =>
    JSON.stringify({
        name,
        input_schema: [
            {
                name: "learning_rate",
                label: "Learning rate",
                type: "number",
                default: 0.0005,
                required: true,
            },
            {
                name: "precision",
                type: "enum",
                default: "bf16",
                options: ["fp32", "bf16", "fp16"],
            },
            { name: "use_cache", type: "boolean", default: true },
        ],
        task_configs: [
            {
                id: "prepare",
                type: "dataset.prepare",
                label: "Prepare dataset",
                position: { x: 40, y: 110 },
                status: "completed",
                source: "def prepare(dataset):\n    return dataset.validate()",
            },
            {
                id: "train",
                type: computeType,
                label: "Train model",
                position: { x: 300, y: 40 },
                status: "completed",
                config: { accelerator: "gpu", precision: "bf16" },
            },
            {
                id: "evaluate",
                type: "metrics.evaluate",
                label: "Evaluate",
                position: { x: 300, y: 180 },
                status: "running",
            },
            {
                id: "publish",
                type: "artifact.publish",
                label: "Publish artifacts",
                position: { x: 570, y: 110 },
                status: "pending",
            },
        ],
        links: [
            { from: "prepare", to: "train", kind: "parallel", status: "completed" },
            { from: "prepare", to: "evaluate", kind: "parallel", status: "running" },
            { from: "train", to: "publish", kind: "dependency", status: "pending" },
            { from: "evaluate", to: "publish", kind: "dependency", status: "pending" },
        ],
        metadata: { mock: true, showcase: true },
    });

interface MockRunOptions {
    backend?: "local" | "molq";
    profile?: string | null;
    schedulerJobId?: string | null;
    results?: Record<string, unknown>;
}

/**
 * A run's directory name: its parameters, ``key=value`` sorted and joined —
 * the same derivation the server applies, so the mock shows what production
 * shows rather than a UUID.
 */
export const mockRunSlug = (id: string, parameters: Record<string, unknown>): string => {
    const parts = Object.keys(parameters)
        .sort()
        .map((key) => `${key}=${String(parameters[key])}`.replace(/[^A-Za-z0-9._=+-]+/g, "-"));
    return parts.length > 0 ? parts.join("_") : id.slice(0, 8);
};

const mockRun = (
    id: string,
    projectId: string,
    experimentId: string,
    status: string,
    createdOffset: number,
    parameters: Record<string, unknown>,
    source: string,
    options: MockRunOptions = {},
): ApiRunResponse => {
    const terminal = status === "succeeded" || status === "failed" || status === "cancelled";
    const schedulerJobId = options.schedulerJobId ?? (options.backend === "molq" ? "482017" : null);
    const name = mockRunSlug(id, parameters);
    return {
        id,
        name,
        path: `projects/${projectId}/experiments/${experimentId}/runs/${name}`,
        ref: `molab:experiment/${experimentId}/run/${id}`,
        projectId,
        experimentId,
        status,
        created: isoAt(createdOffset),
        finished: terminal ? isoAt(createdOffset + 48) : null,
        parameters,
        results: options.results ?? {},
        profile: options.profile ?? (options.backend === "molq" ? "dardel-gpu" : "local"),
        configHash: `sha256:${id.split("-").join("").padEnd(20, "0")}`,
        workflow: {
            source,
            gitCommit: "a1b2c3d",
            codeHash: "sha256:mock-code-feature-page",
            configHash: `sha256:${id}-config`,
        },
        workflowSource: source,
        executorInfo:
            options.backend === "molq"
                ? {
                      backend: "molq",
                      scheduler: "slurm",
                      cluster_name: "dardel.scilifelab.se",
                      scheduler_job_id: schedulerJobId,
                  }
                : { backend: "local" },
        executionHistory:
            status === "pending"
                ? []
                : [
                      {
                          executionId: `exec-${id}-01`,
                          startedAt: isoAt(createdOffset),
                          finishedAt: terminal ? isoAt(createdOffset + 48) : null,
                          status,
                          schedulerJobId,
                      },
                  ],
        error:
            status === "failed"
                ? {
                      type: "RuntimeError",
                      message: "CUDA out of memory while evaluating batch 184; retry with a smaller batch.",
                  }
                : null,
    };
};

/**
 * Create an empty database
 */
function createEmptyDb(): MockDatabase {
    return {
        projects: new Map(),
        experiments: new Map(),
        runs: new Map(),
        assets: new Map(),
        files: new Map(),
        runLogs: new Map(),
    };
}

/**
 * Seed the database with default workspace data
 */
export function seed(): void {
    // Projects
    const projects: ApiProjectResponse[] = [
        {
            id: "protein-folding",
            name: "Protein Folding",
            path: "projects/protein-folding",
            description: "Benchmarking folding pipelines",
            owner: "molab",
            tags: ["biology", "gpu"],
            config: { priority: "high" },
            created: isoAt(-1440),
            experimentCount: 2,
            ref: "molab:project/protein-folding",
        },
        {
            id: "catalyst-search",
            name: "Catalyst Search",
            path: "projects/catalyst-search",
            description: "Screening catalysts for CO2 reduction",
            owner: "molab",
            tags: ["chemistry"],
            config: { priority: "medium" },
            created: isoAt(-2880),
            experimentCount: 1,
            ref: "molab:project/catalyst-search",
        },
    ];

    projects.forEach((p) => db.projects.set(p.id, p));

    // Experiments
    const experiments: Array<ApiExperimentResponse> = [
        {
            id: "exp-001",
            projectId: "protein-folding",
            name: "AlphaFold Baseline",
            path: "projects/protein-folding/experiments/alphafold-baseline",
            description: "Initial baseline run with AF2",
            workflow: workflowIr("alphafold-baseline", "model.alphafold"),
            workflowKind: "document",
            gitCommit: "a1b2c3d",
            parameterSpace: { lr: [0.001, 0.0005] },
            runCount: 4,
            runs: [
                {
                    id: "run-001",
                    statusSummary: { total: 1, active: 0, notStarted: false, byStatus: { succeeded: 1 } },
                    parameters: { batch_size: 32 },
                    created: isoAt(-120),
                },
            ],
            created: isoAt(-1300),
            ref: "molab:experiment/exp-001",
        },
        {
            id: "exp-002",
            projectId: "protein-folding",
            name: "Structure Sweep",
            path: "projects/protein-folding/experiments/structure-sweep",
            description: "Parameter sweep on secondary structure",
            workflow: workflowIr("structure-sweep", "simulation.gromacs"),
            workflowKind: "document",
            gitCommit: "d4e5f6g",
            parameterSpace: { temperature: [0.8, 1.0, 1.2] },
            runCount: 3,
            runs: [],
            created: isoAt(-900),
            ref: "molab:experiment/exp-002",
        },
        {
            id: "exp-101",
            projectId: "catalyst-search",
            name: "Catalyst Sweep",
            path: "projects/catalyst-search/experiments/catalyst-sweep",
            description: "Screening ligand libraries",
            workflow: workflowIr("catalyst-screen", "simulation.dft"),
            workflowKind: "document",
            gitCommit: "h7i8j9k",
            parameterSpace: { ligand: ["L1", "L2", "L3"] },
            runCount: 2,
            runs: [
                {
                    id: "run-101",
                    statusSummary: { total: 1, active: 0, notStarted: false, byStatus: { succeeded: 1 } },
                    parameters: { batch_size: 16 },
                    created: isoAt(-100),
                },
            ],
            created: isoAt(-700),
            ref: "molab:experiment/exp-101",
        },
    ];

    experiments.forEach((e) => db.experiments.set(e.id, e));

    // Runs
    const alphaFoldSource = workflowIr("alphafold-baseline", "model.alphafold");
    const structureSource = workflowIr("structure-sweep", "simulation.gromacs");
    const catalystSource = workflowIr("catalyst-screen", "simulation.dft");
    const runs: ApiRunResponse[] = [
        mockRun(
            "run-001",
            "protein-folding",
            "exp-001",
            "succeeded",
            -120,
            { learning_rate: 0.0005, batch_size: 32, precision: "bf16", use_cache: true },
            alphaFoldSource,
            {
                backend: "molq",
                schedulerJobId: "421337",
                results: { final_loss: 0.142, plddt_mean: 87.4, checkpoint: "asset-003" },
            },
        ),
        {
            ...mockRun(
                "run-002",
                "protein-folding",
                "exp-001",
                "running",
                -92,
                { learning_rate: 0.001, batch_size: 64, precision: "fp16", use_cache: true },
                alphaFoldSource,
                { backend: "molq", schedulerJobId: "421442" },
            ),
            executionHistory: [
                {
                    executionId: "exec-run-002-01",
                    startedAt: isoAt(-180),
                    finishedAt: isoAt(-151),
                    status: "failed",
                    schedulerJobId: "421401",
                },
                {
                    executionId: "exec-run-002-02",
                    startedAt: isoAt(-92),
                    finishedAt: null,
                    status: "running",
                    schedulerJobId: "421442",
                },
            ],
        },
        mockRun(
            "run-003",
            "protein-folding",
            "exp-001",
            "failed",
            -260,
            { learning_rate: 0.002, batch_size: 128, precision: "fp16", use_cache: false },
            alphaFoldSource,
            { backend: "molq", schedulerJobId: "421188" },
        ),
        mockRun(
            "run-004",
            "protein-folding",
            "exp-001",
            "cancelled",
            -410,
            { learning_rate: 0.0001, batch_size: 16, precision: "fp32", use_cache: true },
            alphaFoldSource,
        ),
        mockRun(
            "run-201",
            "protein-folding",
            "exp-002",
            "pending",
            -42,
            { temperature: 0.8, pressure: 1.0, replicas: 4 },
            structureSource,
        ),
        mockRun(
            "run-202",
            "protein-folding",
            "exp-002",
            "running",
            -88,
            { temperature: 1.0, pressure: 1.0, replicas: 8 },
            structureSource,
            { backend: "molq", schedulerJobId: "512004" },
        ),
        mockRun(
            "run-203",
            "protein-folding",
            "exp-002",
            "succeeded",
            -340,
            { temperature: 1.2, pressure: 1.0, replicas: 4 },
            structureSource,
            { results: { rmsd: 1.84, energy_drift: 0.0021, frames: 5000 } },
        ),
        mockRun(
            "run-101",
            "catalyst-search",
            "exp-101",
            "succeeded",
            -100,
            { ligand: "L1", metal: "Cu", batch_size: 16 },
            catalystSource,
            { results: { hit_rate: 0.31, adsorption_energy: -1.42 } },
        ),
        mockRun(
            "run-102",
            "catalyst-search",
            "exp-101",
            "failed",
            -64,
            { ligand: "L2", metal: "Ni", batch_size: 16 },
            catalystSource,
            { backend: "molq", schedulerJobId: "611044" },
        ),
    ];

    runs.forEach((r) => db.runs.set(r.id, r));

    // Assets — unified typed asset model. `extra` carries kind-specific fields.
    const assets: ApiAssetResponse[] = [
        {
            id: "asset-001",
            projectId: "protein-folding",
            title: "qm9",
            name: "qm9",
            kind: "data",
            scopeKind: "workspace",
            scopeIds: [],
            path: "data_assets/asset-001/payload",
            createdAt: isoAt(-2000),
            updatedAt: isoAt(-2000),
            producer: null,
            tags: { source: "s3://datasets/qm9", stage: "training" },
            extra: {
                mime: "application/octet-stream",
                size: 104857600,
                source_path: "s3://datasets/qm9",
                import_action: "copy",
            },
            contentHash:
                "sha256:9c1185a5c5e9fc54612808977ee8f548b2258d31ddadef7c5e9fc54612808977",
        },
        {
            id: "asset-002",
            projectId: "catalyst-search",
            title: "ligands",
            name: "ligands",
            kind: "data",
            scopeKind: "project",
            scopeIds: ["catalyst-search"],
            path: "data_assets/asset-002/payload",
            createdAt: isoAt(-1600),
            updatedAt: isoAt(-1600),
            producer: null,
            tags: { source: "internal", stage: "screening" },
            extra: {
                mime: "text/csv",
                size: 5242880,
                source_path: "/data/ligands.csv",
                import_action: "copy",
            },
        },
        {
            id: "asset-003",
            projectId: "protein-folding",
            title: "alphafold.pt",
            name: "alphafold.pt",
            kind: "artifact",
            scopeKind: "run",
            scopeIds: ["protein-folding", "exp-001", "run-001"],
            path: "artifacts/alphafold.pt",
            createdAt: isoAt(-100),
            updatedAt: isoAt(-100),
            producer: {
                run_id: "run-001",
                executionId: "exec-001",
                task_id: "train",
                inputs: ["asset-001"],
            },
            tags: { role: "checkpoint", epoch: "24" },
            extra: {
                mime: "application/octet-stream",
                size: 20971520,
            },
            contentHash:
                "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        },
        {
            id: "asset-004",
            projectId: "protein-folding",
            title: "run",
            name: "run",
            kind: "log",
            scopeKind: "run",
            scopeIds: ["protein-folding", "exp-001", "run-001"],
            path: "logs/run.log",
            createdAt: isoAt(-120),
            updatedAt: isoAt(-60),
            producer: {
                run_id: "run-001",
                executionId: "exec-001",
                task_id: null,
            },
            tags: {},
            extra: {
                line_count: 142,
                last_tail: "[INFO] run completed successfully",
            },
        },
        {
            id: "asset-005",
            projectId: "protein-folding",
            title: "epoch1",
            name: "epoch1",
            kind: "checkpoint",
            scopeKind: "run",
            scopeIds: ["protein-folding", "exp-001", "run-001"],
            path: ".ckpt/ckpt_abc.json",
            createdAt: isoAt(-80),
            updatedAt: isoAt(-80),
            producer: {
                run_id: "run-001",
                executionId: "exec-001",
                task_id: "train",
                inputs: ["asset-001", "asset-003"],
            },
            tags: {},
            extra: {
                ckpt_id: "ckpt_abc",
                parent_ckpt_id: null,
            },
        },
    ];

    assets.forEach((a) => db.assets.set(a.id, a));

    // File tree
    const fileTree: FileNode[] = [
        {
            name: "workflows",
            path: "/workflows",
            type: "folder",
            children: [
                {
                    name: "alphafold.yml",
                    path: "/workflows/alphafold.yml",
                    type: "file",
                    size: 1024,
                    modified: isoAt(-500),
                    content: `# AlphaFold Protein Structure Prediction
name: alphafold-prediction
version: 2.3.1
description: Predicted protein structure using AlphaFold 2 system.

defaults:
  resources:
    cpu: 4
    memory: "16Gi"
    gpu: "1"

inputs:
  fasta_file:
    type: file
    description: Input protein sequence in FASTA format
  database_dir:
    type: directory
    description: Path to genetic databases

tasks:
  - name: feature_extraction
    image: alphafold:2.3.1
    command:
      - python
      - run_alphafold.py
      - --fasta_paths=\${inputs.fasta_file}
      - --data_dir=\${inputs.database_dir}
      - --output_dir=\${outputs.features}
      - --model_preset=monomer

  - name: structure_prediction
    image: alphafold:2.3.1
    needs: [feature_extraction]
    resources:
      gpu: "1"
    command:
      - python
      - predict_structure.py
      - --features_dir=\${tasks.feature_extraction.outputs.features}
      - --output_path=\${outputs.pdb_file}

outputs:
  pdb_file:
    type: file
    path: predicted_structure.pdb
  confidence_scores:
    type: json
    path: ranking_debug.json`,
                },
                {
                    name: "catalyst.yml",
                    path: "/workflows/catalyst.yml",
                    type: "file",
                    size: 856,
                    modified: isoAt(-400),
                    content: `# Catalyst Screening Pipeline
name: co2-reduction-catalyst-screen
description: High-throughput screening of catalysts for CO2 reduction efficiency.

inputs:
  ligand_library:
    type: file
    format: csv
  metal_centers:
    type: list
    default: ["Cu", "Ni", "Fe"]

tasks:
  - name: generate_structures
    image: openbabel:3.1
    command:
      - obabel
      - -i
      - csv
      - \${inputs.ligand_library}
      - -o
      - sdf
      - -O
      - ligands.sdf
      - --gen3d

  - name: dft_optimization
    image: quantum-espresso:7.0
    needs: [generate_structures]
    parallelism: 10
    command:
      - run_dft.sh
      - --input
      - ligands.sdf
      - --metals
      - \${inputs.metal_centers}

  - name: analysis
    image: python:3.9
    needs: [dft_optimization]
    command:
      - python
      - analyze_results.py
      - --logs
      - \${tasks.dft_optimization.outputs.logs}

outputs:
  top_candidates:
    type: file
    path: candidates.csv`,
                },
                {
                    name: "structure_sweep.yml",
                    path: "/workflows/structure_sweep.yml",
                    type: "file",
                    size: 1200,
                    modified: isoAt(-300),
                    content: `# Secondary Structure Parameter Sweep
name: secondary-structure-sweep
description: Sensitivity analysis of secondary structure parameters.

parameters:
  temperature:
    type: float
    default: 1.0
  pressure:
    type: float
    default: 1.0

tasks:
  - name: prepare_simulation
    image: gromacs:2023
    command:
      - gmx
      - grompp
      - -f
      - gromos.mdp
      - -c
      - protein.gro
      - -p
      - topol.top
      - -o
      - input.tpr

  - name: run_md
    image: gromacs:2023
    needs: [prepare_simulation]
    resources:
      gpu: "1"
    command:
      - gmx
      - mdrun
      - -s
      - input.tpr
      - -temperature
      - \${parameters.temperature}
      - -pressure
      - \${parameters.pressure}

outputs:
  trajectory:
    type: file
    path: traj.xtc
  energy:
    type: file
    path: ener.edr`,
                },
            ],
        },
        {
            name: "data",
            path: "/data",
            type: "folder",
            children: [
                {
                    name: "qm9.h5",
                    path: "/data/qm9.h5",
                    type: "file",
                    size: 104857600,
                    modified: isoAt(-2000),
                },
                {
                    name: "ligands.csv",
                    path: "/data/ligands.csv",
                    type: "file",
                    size: 5242880,
                    modified: isoAt(-1600),
                },
            ],
        },
        {
            name: "models",
            path: "/models",
            type: "folder",
            children: [
                {
                    name: "alphafold.pt",
                    path: "/models/alphafold.pt",
                    type: "file",
                    size: 20971520,
                    modified: isoAt(-100),
                },
            ],
        },
        {
            name: "README.md",
            path: "/README.md",
            type: "file",
            size: 2048,
            modified: isoAt(-3000),
            content: "# Molab Workspace\n\nThis is a mock workspace for development and testing.",
        },
    ];

    // Build file map
    const addToFileMap = (node: FileNode) => {
        db.files.set(node.path, node);
        if (node.children) {
            node.children.forEach(addToFileMap);
        }
    };

    fileTree.forEach(addToFileMap);
}

/**
 * Reset the database to default state (for test isolation)
 */
export function resetDatabase(): void {
    db = createEmptyDb();
    seed();
}

/**
 * Initialize the database on module load
 */
db = createEmptyDb();
seed();

// ============================================================================
// Database Accessors
// ============================================================================

/**
 * Get all projects
 */
export function getAllProjects(): ApiProjectResponse[] {
    return Array.from(db.projects.values());
}

/**
 * Get project by ID
 */
export function getProject(id: string): ApiProjectResponse | undefined {
    return db.projects.get(id);
}

/**
 * Add or update a project
 */
export function setProject(project: ApiProjectResponse): void {
    db.projects.set(project.id, project);
}

/**
 * Delete a project
 */
export function deleteProject(id: string): boolean {
    return db.projects.delete(id);
}

/**
 * Get experiments for a project
 */
export function getExperimentsByProject(projectId: string): ApiExperimentResponse[] {
    return Array.from(db.experiments.values()).filter((e) => e.projectId === projectId);
}

/**
 * Get experiment by ID
 */
export function getExperiment(id: string): ApiExperimentResponse | undefined {
    return db.experiments.get(id);
}

/**
 * Add or update an experiment
 */
export function setExperiment(experiment: ApiExperimentResponse): void {
    db.experiments.set(experiment.id, experiment);
}

/**
 * Delete an experiment
 */
export function deleteExperiment(id: string): boolean {
    return db.experiments.delete(id);
}

/**
 * Get runs for an experiment
 */
export function getRunsByExperiment(experimentId: string): ApiRunResponse[] {
    return Array.from(db.runs.values()).filter((r) => r.experimentId === experimentId);
}

/**
 * Get run by ID
 */
export function getRun(id: string): ApiRunResponse | undefined {
    return db.runs.get(id);
}

/**
 * Add or update a run
 */
export function setRun(run: ApiRunResponse): void {
    db.runs.set(run.id, run);
}

/**
 * Delete a run
 */
export function deleteRun(id: string): boolean {
    return db.runs.delete(id);
}

/**
 * Get all assets
 */
export function getAllAssets(): ApiAssetResponse[] {
    return Array.from(db.assets.values());
}

/**
 * Get assets attributable to a project.
 *
 * An asset belongs to a project when its scope starts at the project or
 * when it was produced by a run inside that project.
 */
export function getAssetsByProject(projectId: string): ApiAssetResponse[] {
    return Array.from(db.assets.values()).filter((asset) => {
        if (asset.scopeKind === "project" && asset.scopeIds[0] === projectId) {
            return true;
        }
        if (
            (asset.scopeKind === "experiment" || asset.scopeKind === "run") &&
            asset.scopeIds[0] === projectId
        ) {
            return true;
        }
        return false;
    });
}

/**
 * Get asset by ID
 */
export function getAsset(id: string): ApiAssetResponse | undefined {
    return db.assets.get(id);
}

/**
 * Add or update an asset.
 */
export function setAsset(asset: ApiAssetResponse): void {
    db.assets.set(asset.id, asset);
}

/**
 * Get file tree (all root-level files)
 */
export function getFileTree(): FileNode[] {
    return Array.from(db.files.values()).filter((f) => {
        const parts = f.path.split("/").filter(Boolean);
        return parts.length === 1; // Root level
    });
}

/**
 * Get file node by path
 */
export function getFile(path: string): FileNode | undefined {
    return db.files.get(path);
}

/**
 * Delete a file or folder by path.
 */
export function deleteFile(path: string): boolean {
    const existing = db.files.get(path);
    if (!existing) {
        return false;
    }

    const prefix = path.endsWith("/") ? path : `${path}/`;
    for (const candidatePath of Array.from(db.files.keys())) {
        if (candidatePath === path || candidatePath.startsWith(prefix)) {
            db.files.delete(candidatePath);
        }
    }

    const parentPath = path.split("/").slice(0, -1).join("/") || "/";
    const parent = db.files.get(parentPath);
    if (parent?.children) {
        parent.children = parent.children.filter((child) => child.path !== path);
    }

    return true;
}

/**
 * Write or update a file
 */
export function writeFile(path: string, content: string): void {
    const existing = db.files.get(path);
    if (existing) {
        existing.content = content;
        existing.size = content.length;
        existing.modified = new Date().toISOString();
    } else {
        const parts = path.split("/").filter(Boolean);
        const name = parts[parts.length - 1];
        const newFile: FileNode = {
            name,
            path,
            type: "file",
            size: content.length,
            modified: new Date().toISOString(),
            content,
        };
        db.files.set(path, newFile);

        // Update parent directory
        const parentPath = "/" + parts.slice(0, -1).join("/");
        const parent = db.files.get(parentPath);
        if (parent && parent.type === "folder") {
            if (!parent.children) {
                parent.children = [];
            }
            parent.children.push(newFile);
        }
    }
}

/**
 * Create a directory
 */
export function createDirectory(path: string): void {
    const existing = db.files.get(path);
    if (existing) return;

    const parts = path.split("/").filter(Boolean);
    const name = parts[parts.length - 1];
    const newDir: FileNode = {
        name,
        path,
        type: "folder",
        modified: new Date().toISOString(),
        children: [],
    };
    db.files.set(path, newDir);

    // Update parent directory
    if (parts.length > 1) {
        const parentPath = "/" + parts.slice(0, -1).join("/");
        const parent = db.files.get(parentPath);
        if (parent && parent.type === "folder") {
            if (!parent.children) {
                parent.children = [];
            }
            parent.children.push(newDir);
        }
    }
}

/**
 * Set run status
 */
export function setRunStatus(runId: string, status: string): void {
    const run = db.runs.get(runId);
    if (run) {
        run.status = status;
        if (status === "succeeded" || status === "failed" || status === "cancelled") {
            run.finished = new Date().toISOString();
        }
    }
}

/**
 * Get run logs
 */
export function getRunLogs(runId: string): string[] {
    return db.runLogs.get(runId) || [];
}

/**
 * Add run log line
 */
export function addRunLog(runId: string, line: string): void {
    const logs = db.runLogs.get(runId) || [];
    logs.push(line);
    db.runLogs.set(runId, logs);
}
