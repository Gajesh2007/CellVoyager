"use client";

import { PropsWithChildren, useMemo } from "react";
import { WagmiProvider } from "wagmi";
import { http } from "wagmi";
import { baseSepolia } from "wagmi/chains";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { getDefaultConfig, RainbowKitProvider, darkTheme } from "@rainbow-me/rainbowkit";
import "@rainbow-me/rainbowkit/styles.css";

export default function Providers({ children }: PropsWithChildren) {
  const queryClient = useMemo(() => new QueryClient(), []);
  const config = useMemo(
    () =>
      getDefaultConfig({
        appName: "CellVoyager",
        projectId: process.env.NEXT_PUBLIC_WC_PROJECT_ID || "demo",
        chains: [baseSepolia],
        transports: {
          [baseSepolia.id]: http(),
        },
        ssr: true,
      }),
    []
  );

  return (
    <WagmiProvider config={config}>
      <QueryClientProvider client={queryClient}>
        <RainbowKitProvider theme={darkTheme()}>{children}</RainbowKitProvider>
      </QueryClientProvider>
    </WagmiProvider>
  );
}


