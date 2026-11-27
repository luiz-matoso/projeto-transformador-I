import { useState, type FormEvent } from "react";
import { Eye, EyeOff } from "lucide-react";
import { login } from "../../services/api";
import { Loading } from "../../components/ui/Loading";
export function Login({
  onLogin,
  expired,
}: {
  onLogin: () => void;
  expired: boolean;
}) {
  const [username, setUsername] = useState(""),
    [password, setPassword] = useState(""),
    [visible, setVisible] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await login(username, password);
      setPassword("");
      onLogin();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível entrar.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-screen">
      <main className="login-card">
        <div className="login-brand">Permear Workspace</div>
        <form className="login-form" onSubmit={submit}>
          <h1>Entrar</h1>
          {expired && (
            <p role="status" className="alert">
              Sua sessão expirou. Entre novamente.
            </p>
          )}
          <label>
            Usuário
            <input
              required
              autoComplete="username"
              maxLength={200}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </label>
          <label>
            Senha
            <div className="password-field">
              <input
                required
                type={visible ? "text" : "password"}
                autoComplete="current-password"
                maxLength={1024}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                className="icon-button"
                type="button"
                aria-label={visible ? "Ocultar senha" : "Mostrar senha"}
                onClick={() => setVisible(!visible)}
              >
                {visible ? <EyeOff size={17} /> : <Eye size={17} />}
              </button>
            </div>
          </label>
          {error && (
            <div role="alert" className="alert error">
              {error}
            </div>
          )}
          <button type="submit" className="primary" disabled={busy}>
            {busy ? "Conectando…" : "Entrar"}
          </button>
        </form>
      </main>
    </div>
  );
}
