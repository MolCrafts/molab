import { createContext } from "react";
import type { MolabRefTarget } from "@/lib/molab-ref";

export const MolabRefIndexContext = createContext<ReadonlyMap<string, MolabRefTarget> | null>(null);
