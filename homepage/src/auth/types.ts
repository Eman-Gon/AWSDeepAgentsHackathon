export type UserRole = 'journalist' | 'editor';

export interface AuthPermissions {
  canInvestigate: boolean;
  canPublish: boolean;
}

export interface AuthSession {
  isAuthenticated: boolean;
  userName: string;
  email: string;
  roles: UserRole[];
  isHuman: boolean;
  permissions: AuthPermissions;
}
