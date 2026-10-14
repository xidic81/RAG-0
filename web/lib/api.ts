export type Citation = {
  filename: string;
  page: number;
};

export type ChatResponse = {
  conversation_id: string;
  message_id: string;
  answer: string;
  citations: Citation[];
};

export type Doc = {
  id: string;
  filename: string;
  page_count: number | null;
  status: "pending" | "processing" | "ready" | "failed";
  error: string | null;
  ingested_at: string;
};

export type Health = {
  postgres: string;
  pinecone: string;
  llm_provider: "groq" | "ollama";
  llm: string;
};

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch("/api" + path, init);

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    if (
      response.status === 401 &&
      path !== "/auth/login" &&
      path !== "/auth/session" &&
      typeof window !== "undefined"
    ) {
      window.dispatchEvent(new Event("auth-expired"));
    }
    throw new ApiError(body.detail ?? response.statusText, response.status);
  }

  return response.json() as Promise<T>;
}

export function authSession(): Promise<{ authenticated: boolean }> {
  return request<{ authenticated: boolean }>("/auth/session");
}

export function login(username: string, password: string): Promise<{ authenticated: boolean }> {
  return request<{ authenticated: boolean }>("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
}

export function logout(): Promise<{ authenticated: boolean }> {
  return request<{ authenticated: boolean }>("/auth/logout", { method: "POST" });
}

export function chat(message: string, conversationId: string | null): Promise<ChatResponse> {
  return request<ChatResponse>("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, conversation_id: conversationId }),
  });
}

export function listDocuments(): Promise<Doc[]> {
  return request<Doc[]>("/documents");
}

export function uploadDocument(file: File): Promise<{ filename: string; status: string }> {
  const formData = new FormData();
  formData.append("file", file);

  return request<{ filename: string; status: string }>("/documents", {
    method: "POST",
    body: formData,
  });
}

export function deleteDocument(id: string): Promise<{ deleted: string }> {
  return request<{ deleted: string }>(`/documents/${id}`, {
    method: "DELETE",
  });
}

export function health(): Promise<Health> {
  return request<Health>("/health");
}