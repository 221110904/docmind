import { createContext, useContext } from "react";

export interface Auth {
  /** false when login is switched off (VITE_AUTH=off), as in local development */
  enabled: boolean;
  status: "loading" | "signed-out" | "signed-in";
  name: string | null;
  /** why the last sign-in attempt failed, if it did */
  error: string | null;
  signIn: () => void;
  signOut: () => void;
}

export const LOGIN_OFF: Auth = {
  enabled: false,
  status: "signed-in",
  name: null,
  error: null,
  signIn: () => {},
  signOut: () => {},
};

export const AuthContext = createContext<Auth>(LOGIN_OFF);

export function useAuth(): Auth {
  return useContext(AuthContext);
}
