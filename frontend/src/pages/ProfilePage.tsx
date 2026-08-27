import { useState, type FormEvent } from "react";
import { KeyRound, Save } from "lucide-react";

import {
  Alert,
  Button,
  Card,
  CardHeader,
  Field,
  Input,
  Select,
} from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { User } from "@/lib/types";
import { ROLE_LABELS, useAuthStore } from "@/store/auth";
import { formatDate } from "@/lib/utils";

const BUSINESS_TYPES = [
  "Công ty TNHH một thành viên",
  "Công ty TNHH hai thành viên trở lên",
  "Công ty cổ phần",
  "Doanh nghiệp tư nhân",
  "Hộ kinh doanh",
];

export function ProfilePage() {
  const user = useAuthStore((state) => state.user);
  const setUser = useAuthStore((state) => state.setUser);

  const [profileState, setProfileState] = useState<{ error?: string; ok?: string }>({});
  const [passwordState, setPasswordState] = useState<{ error?: string; ok?: string }>({});
  const [savingProfile, setSavingProfile] = useState(false);
  const [savingPassword, setSavingPassword] = useState(false);

  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [org, setOrg] = useState({
    name: user?.organization?.name ?? "",
    tax_code: user?.organization?.tax_code ?? "",
    business_type: user?.organization?.business_type ?? BUSINESS_TYPES[0],
    employee_count: user?.organization?.employee_count ?? 0,
    vat_period: user?.organization?.vat_period ?? "quarterly",
    address: user?.organization?.address ?? "",
  });

  if (!user) return null;

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    setSavingProfile(true);
    setProfileState({});
    try {
      const { data } = await api.patch<User>("/api/v1/auth/me", {
        full_name: fullName,
        organization: org.name
          ? {
              ...org,
              tax_code: org.tax_code || null,
              address: org.address || null,
              employee_count: Number(org.employee_count) || 0,
            }
          : null,
      });
      setUser(data);
      setProfileState({ ok: "Đã lưu hồ sơ. Lịch tuân thủ đã được sinh lại theo thông tin mới." });
    } catch (caught) {
      setProfileState({ error: errorMessage(caught, "Không lưu được hồ sơ") });
    } finally {
      setSavingProfile(false);
    }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault();
    const form = event.target as HTMLFormElement;
    const data = new FormData(form);
    const next = String(data.get("new_password") ?? "");

    if (next !== String(data.get("confirm_password") ?? "")) {
      setPasswordState({ error: "Mật khẩu mới nhập lại không khớp" });
      return;
    }

    setSavingPassword(true);
    setPasswordState({});
    try {
      await api.post("/api/v1/auth/change-password", {
        current_password: data.get("current_password"),
        new_password: next,
      });
      form.reset();
      setPasswordState({ ok: "Đã đổi mật khẩu" });
    } catch (caught) {
      setPasswordState({ error: errorMessage(caught, "Không đổi được mật khẩu") });
    } finally {
      setSavingPassword(false);
    }
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-2xl space-y-4 px-4 py-6">
        <header>
          <h1 className="text-xl font-semibold text-ink">Hồ sơ</h1>
          <p className="mt-1 text-sm text-muted">
            {user.email} · {ROLE_LABELS[user.role]} · tham gia {formatDate(user.created_at)}
          </p>
        </header>

        <Card>
          <CardHeader
            title="Thông tin doanh nghiệp"
            description="Số lao động và kỳ khai thuế quyết định những nghĩa vụ nào xuất hiện trong lịch tuân thủ."
          />
          <form className="space-y-4 p-5" onSubmit={saveProfile}>
            {profileState.error && <Alert>{profileState.error}</Alert>}
            {profileState.ok && <Alert tone="ok">{profileState.ok}</Alert>}

            <Field label="Họ và tên">
              <Input value={fullName} onChange={(event) => setFullName(event.target.value)} required />
            </Field>

            <Field label="Tên doanh nghiệp" hint="Để trống nếu bạn dùng tài khoản cá nhân">
              <Input
                value={org.name}
                onChange={(event) => setOrg({ ...org, name: event.target.value })}
                placeholder="Công ty TNHH ABC"
              />
            </Field>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Mã số thuế">
                <Input
                  value={org.tax_code}
                  onChange={(event) => setOrg({ ...org, tax_code: event.target.value })}
                  placeholder="0101234567"
                />
              </Field>
              <Field label="Số lao động">
                <Input
                  type="number"
                  min={0}
                  value={org.employee_count}
                  onChange={(event) =>
                    setOrg({ ...org, employee_count: Number(event.target.value) })
                  }
                />
              </Field>
              <Field label="Loại hình">
                <Select
                  value={org.business_type}
                  onChange={(event) => setOrg({ ...org, business_type: event.target.value })}
                >
                  {BUSINESS_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Kỳ khai thuế GTGT">
                <Select
                  value={org.vat_period}
                  onChange={(event) => setOrg({ ...org, vat_period: event.target.value })}
                >
                  <option value="monthly">Theo tháng</option>
                  <option value="quarterly">Theo quý</option>
                </Select>
              </Field>
            </div>

            <Field label="Địa chỉ">
              <Input
                value={org.address}
                onChange={(event) => setOrg({ ...org, address: event.target.value })}
              />
            </Field>

            <Button type="submit" loading={savingProfile}>
              <Save className="size-4" aria-hidden />
              Lưu hồ sơ
            </Button>
          </form>
        </Card>

        <Card>
          <CardHeader title="Đổi mật khẩu" />
          <form className="space-y-4 p-5" onSubmit={changePassword}>
            {passwordState.error && <Alert>{passwordState.error}</Alert>}
            {passwordState.ok && <Alert tone="ok">{passwordState.ok}</Alert>}

            <Field label="Mật khẩu hiện tại">
              <Input name="current_password" type="password" required autoComplete="current-password" />
            </Field>
            <Field label="Mật khẩu mới" hint="Ít nhất 8 ký tự">
              <Input
                name="new_password"
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
              />
            </Field>
            <Field label="Nhập lại mật khẩu mới">
              <Input name="confirm_password" type="password" required autoComplete="new-password" />
            </Field>

            <Button type="submit" variant="secondary" loading={savingPassword}>
              <KeyRound className="size-4" aria-hidden />
              Đổi mật khẩu
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
