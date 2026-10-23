"use client";
import { useConvexAuth } from "convex/react";
import Heatmap from "./Heatmap";
import SignIn from "./SignIn";

export default function Home() {
  const { isLoading, isAuthenticated } = useConvexAuth();
  if (isLoading) return <p className="hm-wait">Loading…</p>;
  return isAuthenticated ? <Heatmap /> : <SignIn />;
}
