import { useEffect, useState } from "react";

/** An object URL for a blob, revoked when the blob changes or the view unmounts. */
export const useObjectUrl = (blob: Blob | undefined): string | null => {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!blob) {
      setUrl(null);
      return;
    }
    const next = URL.createObjectURL(blob);
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [blob]);
  return url;
};
