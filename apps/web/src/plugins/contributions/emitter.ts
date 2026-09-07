export type ContributionListener = () => void;

export class Emitter {
  private listeners = new Set<ContributionListener>();

  constructor(private readonly label: string) {}

  subscribe(listener: ContributionListener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  emit(): void {
    for (const listener of this.listeners) {
      try {
        listener();
      } catch (err) {
        console.error(`[molexp-plugin] ${this.label} listener failed`, err);
      }
    }
  }
}
