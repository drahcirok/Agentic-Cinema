"use client";

import { GoogleAuthProvider, onAuthStateChanged, signInWithPopup, signOut as firebaseSignOut, type User } from "firebase/auth";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { firebaseIsConfigured, getFirebaseAuth } from "@/lib/firebase";

type AuthContextValue = {
  user: User | null;
  loading: boolean;
  configured: boolean;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
  getAuthHeaders: () => Promise<Record<string, string>>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(firebaseIsConfigured);

  useEffect(() => {
    if (!firebaseIsConfigured) return;
    return onAuthStateChanged(getFirebaseAuth(), (nextUser) => {
      setUser(nextUser);
      setLoading(false);
    });
  }, []);

  const signIn = useCallback(async () => {
    const provider = new GoogleAuthProvider();
    provider.setCustomParameters({ prompt: "select_account" });
    await signInWithPopup(getFirebaseAuth(), provider);
  }, []);
  const signOut = useCallback(async () => { await firebaseSignOut(getFirebaseAuth()); }, []);
  const getAuthHeaders = useCallback(async () => {
    if (!user) throw new Error("Your session is no longer available. Please sign in again.");
    return { Authorization: `Bearer ${await user.getIdToken()}` };
  }, [user]);

  const value = useMemo(() => ({ user, loading, configured: firebaseIsConfigured, signIn, signOut, getAuthHeaders }), [user, loading, signIn, signOut, getAuthHeaders]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider.");
  return context;
}
