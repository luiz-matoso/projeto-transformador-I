import { useEffect, useState, type ReactNode } from "react";
export function useFileURL(file: File | null | undefined) {
  const [url, setURL] = useState("");
  useEffect(() => {
    if (!file) {
      setURL("");
      return;
    }
    const next = URL.createObjectURL(file);
    setURL(next);
    return () => URL.revokeObjectURL(next);
  }, [file]);
  return url;
}
export function Notice({
  children,
  error = false,
}: {
  children: ReactNode;
  error?: boolean;
}) {
  return (
    <div
      role={error ? "alert" : "status"}
      className={error ? "alert error" : "alert"}
    >
      {children}
    </div>
  );
}
