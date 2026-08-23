import { MainLayout } from "@/components/layout/MainLayout";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { ChatWindow } from "@/components/chat/ChatWindow";

import { getTranslations } from "next-intl/server";
import { useTranslations } from "next-intl";

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "metadata" });
  return {
    title: t("chat_title"),
    description: t("chat_desc"),
  };
}

export default function ChatPage() {
  const t = useTranslations("chat");
  return (
    <ProtectedRoute>
      <MainLayout>
        <div className="mx-auto max-w-3xl px-4 py-6">
          <div className="mb-4">
            <h1 className="text-2xl font-bold">{t("title")}</h1>
            <p className="text-sm text-muted-foreground">{t("description")}</p>
          </div>
          <ChatWindow />
        </div>
      </MainLayout>
    </ProtectedRoute>
  );
}
