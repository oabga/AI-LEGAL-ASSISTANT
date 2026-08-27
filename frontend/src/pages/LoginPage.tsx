import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Scale } from "lucide-react";

import { Alert, Button, Field, Input } from "@/components/ui";
import { useAuthStore } from "@/store/auth";

export function LoginPage() {
  const login = useAuthStore((state) => state.login);
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password);
      navigate("/chat", { replace: true });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Đăng nhập thất bại");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grid min-h-full place-items-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-7 text-center">
          <span className="mx-auto mb-3 grid size-11 place-items-center rounded-xl bg-brand text-white">
            <Scale className="size-5" aria-hidden />
          </span>
          <h1 className="text-xl font-semibold text-ink">Trợ lý Pháp lý AI</h1>
          <p className="mt-1 text-sm text-muted">
            Tra cứu và áp dụng pháp luật doanh nghiệp Việt Nam
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && <Alert>{error}</Alert>}
          <Field label="Email">
            <Input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              placeholder="ketoan@congty.vn"
              required
            />
          </Field>
          <Field label="Mật khẩu">
            <Input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          </Field>
          <Button type="submit" size="lg" className="w-full justify-center" loading={submitting}>
            Đăng nhập
          </Button>
        </form>

        <p className="mt-5 text-center text-sm text-muted">
          Chưa có tài khoản?{" "}
          <Link to="/register" className="text-brand hover:underline">
            Đăng ký
          </Link>
        </p>
      </div>
    </div>
  );
}
