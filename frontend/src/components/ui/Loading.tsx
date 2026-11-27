import { LoaderCircle } from "lucide-react";
export function Loading() {
  return (
    <>
      <LoaderCircle size={16} className="animate-spin" aria-hidden="true" />
      <span role="status">Carregando...</span>
    </>
  );
}
export function Skeleton() {
  return <div className="skeleton" role="status" aria-label="Carregando" />;
}
