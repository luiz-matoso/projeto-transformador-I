import {
  ArrowUpRight,
  Database,
  PenLine,
  SlidersHorizontal,
  ScanLine,
} from "lucide-react";
export function HomePage({ navigate }: { navigate: (page: string) => void }) {
  const modules = [
    {
      page: "dataset",
      name: "Dataset",
      description: "Abrir imagens e anotações locais.",
      icon: Database,
    },
    {
      page: "anotacao",
      name: "Anotação",
      description: "Delimitar a faixa de circulação e revisar atributos.",
      icon: PenLine,
    },
    {
      page: "demonstracao/perfis",
      name: "Perfis",
      description: "Configurar necessidades funcionais de deslocamento.",
      icon: SlidersHorizontal,
    },
    {
      page: "demonstracao/analisar",
      name: "Analisar trecho",
      description: "Analisar uma fotografia com dois perfis.",
      icon: ScanLine,
    },
  ];
  return (
    <div className="page home-page">
      <header className="page-heading">
        <h1>Olá!</h1>
      </header>
      <div className="module-list">
        {modules.map((module) => (
          <a
            className="module-card"
            key={module.page}
            href={import.meta.env.BASE_URL + module.page}
            onClick={(e) => {
              e.preventDefault();
              navigate(module.page);
            }}
          >
            <span className="module-visual">
              <module.icon size={25} />
            </span>
            <div>
              <h2>{module.name}</h2>
              <p>{module.description}</p>
            </div>
            <span className="module-action">
              Abrir
              <ArrowUpRight size={14} />
            </span>
          </a>
        ))}
      </div>
    </div>
  );
}
