export interface User {
  id: string;
  email: string;
  displayName: string;
  role: string;
}

export interface Case {
  id: string;
  name: string;
  description: string;
  status: string;
  createdAt: string;
}

export interface ApiError {
  detail: string;
}
