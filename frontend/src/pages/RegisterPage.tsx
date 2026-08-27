import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Scale } from "lucide-react";

import { Alert, Button, Field, Input, Select } from "@/components/ui";
import type { UserRole } from "@/lib/types";
import { ROLE_LABELS, useAuthStore } from "@/store/auth";

const ROLE_OPTIONS: UserRole[] = ["owner", "accountant", "hr"];

const BUSINESS_TYPES = [
  { value: "llc", label: "Công ty TNHH" },
  { value: "jsc", label: "Công ty cổ phần" },
  { value: "private", label: "Doanh nghiệp tư nhân" },
  { value: "partnership", label: "Công ty hợp danh" },
  { value: "household", label: "Hộ kinh doanh" },
];

const VAT_PERIODS = [
  { value: "quarterly", label: "Theo quý" },
  { value: "monthly", label: "Theo tháng" },
];

export function RegisterPage() {
  const register = useAuthStore((state) => state.register);
  const navigate = useNavigate();

  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
    role: "owner" as UserRole,
    orgName: "",
    taxCode: "",
    businessType: "llc",
    employeeCount: "10",
    vatPeriod: "quarterly",
  });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function update<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((previous) => ({ ...previous, [key]: value }));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await register({
        email: form.email.trim(),
        password: form.password,
        full_name: form.full_name.trim(),
        role: form.role,
        // Hồ sơ doanh nghiệp quyết định lịch tuân thủ được sinh ra, nên thu ngay
        // khi đăng ký để dashboard không rỗng.
        organization: form.orgName.trim()
          ? {
              name: form.orgName.trim(),
              tax_code: form.taxCode.trim() || null,
              business_type: form.businessType,
              employee_count: Number(form.employeeCount) || 0,
              vat_period: form.vatPeriod,
            }
          : null,
      });
      navigate("/chat", { replace: true });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Đăng ký thất bại");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grid min-h-full place-items-center px-4 py-10">
      <div className="w-full max-w-lg">
        <div className="mb-7 text-center">
          <span className="mx-auto mb-3 grid size-11 place-items-center rounded-xl bg-brand text-white">
            <Scale className="size-5" aria-hidden />
          </span>
          <h1 className="text-xl font-semibold text-ink">Tạo tài khoản</h1>
          <p className="mt-1 text-sm text-muted">
            Khai hồ sơ doanh nghiệp để hệ thống sinh sẵn lịch tuân thủ phù hợp
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && <Alert>{error}</Alert>}

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Họ và tên">
              <Input
                value={form.full_name}
                onChange={(event) => update("full_name", event.target.value)}
                placeholder="Nguyễn Văn A"
                required
              />
            </Field>
            <Field label="Vai trò">
              <Select
                value={form.role}
                onChange={(event) => update("role", event.target.value as UserRole)}
              >
                {ROLE_OPTIONS.map((role) => (
                  <option key={role} value={role}>
                    {ROLE_LABELS[role]}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          <Field label="Email">
            <Input
              type="email"
              value={form.email}
              onChange={(event) => update("email", event.target.value)}
              autoComplete="email"
              required
            />
          </Field>

          <Field
            label="Mật khẩu"
            hint="Tối thiểu 8 ký tự, có cả chữ và số"
          >
            <Input
              type="password"
              value={form.password}
              onChange={(event) => update("password", event.target.value)}
              autoComplete="new-password"
              minLength={8}
              required
            />
          </Field>

          <fieldset className="space-y-4 rounded-2xl border border-line bg-surface p-4">
            <legend className="px-1 text-sm font-medium text-ink">
              Hồ sơ doanh nghiệp{" "}
              <span className="font-normal text-muted-2">(có thể bổ sung sau)</span>
            </legend>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Tên doanh nghiệp">
                <Input
                  value={form.orgName}
                  onChange={(event) => update("orgName", event.target.value)}
                  placeholder="Công ty TNHH ABC"
                />
              </Field>
              <Field label="Mã số thuế">
                <Input
                  value={form.taxCode}
                  onChange={(event) => update("taxCode", event.target.value)}
                  placeholder="0101234567"
                />
              </Field>
              <Field label="Loại hình">
                <Select
                  value={form.businessType}
                  onChange={(event) => update("businessType", event.target.value)}
                >
                  {BUSINESS_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Số lao động">
                <Input
                  type="number"
                  min={0}
                  value={form.employeeCount}
                  onChange={(event) => update("employeeCount", event.target.value)}
                />
              </Field>
              <Field
                label="Kỳ khai thuế GTGT"
                hint="Quyết định nghĩa vụ khai theo tháng hay theo quý"
              >
                <Select
                  value={form.vatPeriod}
                  onChange={(event) => update("vatPeriod", event.target.value)}
                >
                  {VAT_PERIODS.map((period) => (
                    <option key={period.value} value={period.value}>
                      {period.label}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
          </fieldset>

          <Button type="submit" size="lg" className="w-full justify-center" loading={submitting}>
            Đăng ký
          </Button>
        </form>

        <p className="mt-5 text-center text-sm text-muted">
          Đã có tài khoản?{" "}
          <Link to="/login" className="text-brand hover:underline">
            Đăng nhập
          </Link>
        </p>
      </div>
    </div>
  );
}
