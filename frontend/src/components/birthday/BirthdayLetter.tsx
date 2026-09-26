// SPDX-License-Identifier: MIT
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useWS } from "../../stores/ws";

export function BirthdayLetter() {
  const { t } = useTranslation();
  const letter = useWS((s) => s.birthdayLetter as string | null);
  const [dismissed, setDismissed] = useState(false);

  if (!letter || dismissed) return null;
  const paragraphs = letter.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean);

  return (
    <div
      data-testid="birthday-letter"
      data-opaque="true"
      className="fixed inset-0 z-[80] flex items-center justify-center overflow-auto p-6"
      style={{
        background:
          "radial-gradient(120% 90% at 50% 0%, #2a211a 0%, #171310 68%), #171310",
      }}
    >
      <div
        className="relative my-8 w-full max-w-[640px] px-10 py-12"
        style={{
          color: "#3b3128",
          fontFamily:
            '"Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif',
          fontSize: "16px",
          lineHeight: 1.95,
          borderRadius: "3px",
          background:
            "radial-gradient(115% 100% at 50% 0%, rgba(255,255,255,.5) 0%, rgba(255,255,255,0) 42%), radial-gradient(100% 100% at 50% 100%, rgba(120,92,54,.22) 0%, rgba(120,92,54,0) 46%), linear-gradient(168deg, #f1e6cf 0%, #e9dbbf 46%, #ddcba8 100%)",
          boxShadow:
            "0 18px 44px rgba(0,0,0,.45), inset 0 0 0 1px rgba(255,255,255,.45), inset 0 0 42px rgba(150,116,66,.2)",
        }}
      >
        <div data-testid="birthday-paragraphs" className="flex flex-col gap-5">
          {paragraphs.map((text, i) => (
            <p key={i} className={i === paragraphs.length - 1 ? "text-right italic" : ""}>
              {text}
            </p>
          ))}
        </div>
        <div className="mt-10 flex justify-center">
          <button
            type="button"
            onClick={() => setDismissed(true)}
            className="rounded-full border px-6 py-2 text-sm"
            style={{ borderColor: "rgba(90,72,48,.45)", color: "#5a4830" }}
          >
            {t("birthday.continue")}
          </button>
        </div>
      </div>
    </div>
  );
}
