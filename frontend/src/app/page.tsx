"use client";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { useState, useMemo } from "react";
import { useAccount, useWriteContract, useReadContract, usePublicClient } from "wagmi";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Skeleton } from "@/components/ui/skeleton";
import { parseUnits, formatUnits } from "viem";
import { encryptUrlEnvelope } from "@/lib/crypto";
import governanceAbi from "@/abi/GovernanceQueue.json";
import donationAbi from "@/abi/DonationSBT.json";


const erc20Abi = [
	{ type: "function", name: "approve", stateMutability: "nonpayable", inputs: [{ name: "spender", type: "address" }, { name: "value", type: "uint256" }], outputs: [{ type: "bool" }] },
	{ type: "function", name: "allowance", stateMutability: "view", inputs: [{ name: "owner", type: "address" }, { name: "spender", type: "address" }], outputs: [{ type: "uint256" }] },
	{ type: "function", name: "balanceOf", stateMutability: "view", inputs: [{ name: "account", type: "address" }], outputs: [{ type: "uint256" }] },
	{ type: "function", name: "decimals", stateMutability: "view", inputs: [], outputs: [{ type: "uint8" }] },
];


const GOV_ADDR = (process.env.NEXT_PUBLIC_GOV_ADDRESS || process.env.GOV_ADDRESS) as `0x${string}` | undefined;
const SBT_ADDR = (process.env.NEXT_PUBLIC_SBT_ADDRESS || process.env.SBT_ADDRESS) as `0x${string}` | undefined;
const DONATION_TOKEN_ADDR = ((process.env.NEXT_PUBLIC_DONATION_TOKEN || process.env.DONATION_TOKEN) as `0x${string}` | undefined) ||
  ("0xd20799e08a35A645c16c2cE5cADdCEC3e440B3e0" as `0x${string}`);

export default function Home() {
	const [tab, setTab] = useState("provider");
	const { isConnected, address } = useAccount();
	const { writeContractAsync } = useWriteContract();
  const publicClient = usePublicClient();
  const queryClient = useQueryClient();

	const [form, setForm] = useState({
		analysisName: "",
		description: "",
		datasetUrl: "",
		modelName: "o3-mini",
		numAnalyses: 1,
		maxIterations: 3,
	});

	async function onSubmitProvider() {
		if (!GOV_ADDR) return alert("Missing NEXT_PUBLIC_GOV_ADDRESS");
		if (!publicClient) return alert("Public client not ready");
		const pem = await publicClient.readContract({ address: GOV_ADDR, abi: governanceAbi as any, functionName: "publicEncryptionKey", args: [] }) as string;
		if (!pem) return alert("Public key not set on-chain");
		const encryptedUrl = await encryptUrlEnvelope(pem, form.datasetUrl);
		const hash = await writeContractAsync({
			abi: governanceAbi as any,
			address: GOV_ADDR,
			functionName: "addResearch",
			args: [
				form.analysisName,
				form.description,
				encryptedUrl,
				form.modelName,
				BigInt(form.numAnalyses),
				BigInt(form.maxIterations),
			],
		});
		if (hash && publicClient) {
			await publicClient.waitForTransactionReceipt({ hash });
			queryClient.invalidateQueries({ queryKey: ["count"] });
			queryClient.invalidateQueries({ queryKey: ["queue"] });
		}
		setForm({ analysisName: "", description: "", datasetUrl: "", modelName: "o3-mini", numAnalyses: 1, maxIterations: 3 });
	}

	const [donation, setDonation] = useState({ token: DONATION_TOKEN_ADDR, amount: "" });
	async function onDonate() {
		if (!SBT_ADDR) return alert("Missing NEXT_PUBLIC_SBT_ADDRESS");
		if (!publicClient) return alert("Public client not ready");
		const decsData = await (async () => {
			try {
				return await publicClient.readContract({ address: DONATION_TOKEN_ADDR, abi: erc20Abi as any, functionName: "decimals", args: [] });
			} catch {
				return 18;
			}
		})();
		const decs = Number(decsData ?? 18);
		const amount = parseUnits(donation.amount || "0", decs);
		let hash = await writeContractAsync({ abi: erc20Abi as any, address: DONATION_TOKEN_ADDR, functionName: "approve", args: [SBT_ADDR, amount] });
		if (hash && publicClient) await publicClient.waitForTransactionReceipt({ hash });
		hash = await writeContractAsync({ abi: donationAbi as any, address: SBT_ADDR, functionName: "donate", args: [DONATION_TOKEN_ADDR, amount] });
		if (hash && publicClient) await publicClient.waitForTransactionReceipt({ hash });
		queryClient.invalidateQueries({ queryKey: ["votes"] });
	}

	const { data: count } = useQuery<number>({
    queryKey: ["count", GOV_ADDR],
    queryFn: async () => {
      if (!GOV_ADDR || !publicClient) return 0;
      const res = await publicClient.readContract({ address: GOV_ADDR, abi: governanceAbi as any, functionName: "researchCount", args: [] });
      return Number(res || 0);
    },
	    refetchOnWindowFocus: false,
	    refetchOnReconnect: false,
	    staleTime: 30_000,
	    gcTime: 300_000,
	    placeholderData: (prev) => (typeof prev === "number" ? prev : 0),
	  });
  const items = useMemo(() => Number(count || 0), [count]);

	const { data: queue = [] as any[], isLoading: queueLoading } = useQuery<any[]>({
		queryKey: ["queue", items, GOV_ADDR],
		queryFn: async () => {
			if (!GOV_ADDR || !publicClient) return [] as any[];
			if (!items) return [] as any[];
			const range: any = await publicClient.readContract({ address: GOV_ADDR, abi: governanceAbi as any, functionName: "getResearchRange", args: [BigInt(0), BigInt(items)] });
			const arr = (range as any[]).map((r: any, i: number) => {
				const analysisName = r?.analysisName ?? r?.[0] ?? "";
				const description = r?.description ?? r?.[1] ?? "";
				const modelName = r?.modelName ?? r?.[3] ?? "";
				const createdAt = Number(r?.createdAt ?? r?.[7] ?? 0);
				const priority = BigInt((r?.priority ?? r?.[10] ?? 0).toString());
				const completed = Boolean(r?.completed ?? r?.[8] ?? false);
				return { id: i, analysisName, description, modelName, priority, createdAt, completed };
			});
			// Cache by id in memory to avoid flicker (basic memo across calls)
			return arr.sort((a, b) => (Number(b.priority - a.priority) || (a.createdAt - b.createdAt)));
		},
			enabled: !!GOV_ADDR && items > 0,
		refetchOnWindowFocus: false,
		refetchOnReconnect: false,
		staleTime: 30_000,
		gcTime: 300_000,
		placeholderData: (prev) => (Array.isArray(prev) ? prev : [] as any[]),
	});

	// Stats
	const { data: votesBn } = useReadContract({
		abi: donationAbi as any,
		address: SBT_ADDR,
		functionName: "balanceOf",
		args: address ? [address] : undefined as any,
	});
	const { data: decsBn } = useReadContract({
		abi: erc20Abi as any,
		address: DONATION_TOKEN_ADDR,
		functionName: "decimals",
		args: [],
	});
	const { data: donatedBn } = useReadContract({
		abi: donationAbi as any,
		address: SBT_ADDR,
		functionName: "donatedAmount",
		args: address ? [address, DONATION_TOKEN_ADDR] : undefined as any,
	});
	const { data: lastBump } = useReadContract({
		abi: governanceAbi as any,
		address: GOV_ADDR,
		functionName: "lastBumpAt",
		args: address ? [address] : undefined as any,
	});
	const { data: cooldown } = useReadContract({
		abi: governanceAbi as any,
		address: GOV_ADDR,
		functionName: "COOLDOWN_SECONDS",
		args: [],
	});

	const votes = votesBn ? BigInt(votesBn as any) : BigInt(0);
	const decs = decsBn != null ? Number(decsBn) : 18;
	const votesDisplay = formatUnits(votes, 18);
	const donatedExact = donatedBn ? BigInt(donatedBn as any) : BigInt(0);
	const donatedDisplay = formatUnits(donatedExact, decs);
	const last = lastBump ? Number(lastBump) : 0;
	const cd = cooldown ? Number(cooldown) : 0;
	const now = Math.floor(Date.now() / 1000);
	const remaining = Math.max(0, cd - (now - last));

	async function vote(id: number) {
		if (!GOV_ADDR) return;
		const hash = await writeContractAsync({ abi: governanceAbi as any, address: GOV_ADDR, functionName: "bumpPriority", args: [BigInt(id)] });
		if (hash && publicClient) await publicClient.waitForTransactionReceipt({ hash });
		queryClient.invalidateQueries({ queryKey: ["queue"] });
	}

  return (
		<div className="min-h-screen p-6 space-y-6">
			<div className="flex items-center justify-between">
				<h1 className="text-2xl font-semibold">CellVoyager</h1>
				<ConnectButton />
			</div>
			<Tabs value={tab} onValueChange={setTab}>
				<TabsList>
					<TabsTrigger value="provider">Data Provider</TabsTrigger>
					<TabsTrigger value="donor">Donor</TabsTrigger>
				</TabsList>
				<TabsContent value="provider">
					<Card>
						<CardHeader>
							<CardTitle>Submit Research</CardTitle>
						</CardHeader>
						<CardContent className="space-y-4">
							<Card>
								<CardHeader>
									<CardTitle className="text-base">Your Stats</CardTitle>
								</CardHeader>
								<CardContent className="grid md:grid-cols-3 gap-4 text-sm">
									<div>
										<div className="text-muted-foreground">Governance Power (votes)</div>
										<div className="font-medium">{votesDisplay}</div>
									</div>
									<div>
										<div className="text-muted-foreground">Approx Donated</div>
										<div className="font-medium">{donatedDisplay}</div>
									</div>
									<div>
										<div className="text-muted-foreground">Cooldown Remaining</div>
										<div className="font-medium">{remaining > 0 ? `${remaining}s` : "Ready"}</div>
									</div>
								</CardContent>
							</Card>
							<div className="grid gap-2">
								<Label>Analysis Name</Label>
								<Input value={form.analysisName} onChange={(e) => setForm({ ...form, analysisName: e.target.value })} />
							</div>
							<div className="grid gap-2">
								<Label>Description</Label>
								<Textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
							</div>
							<div className="grid gap-2">
								<Label>Dataset Link (URL)</Label>
								<Input value={form.datasetUrl} onChange={(e) => setForm({ ...form, datasetUrl: e.target.value })} placeholder="https://.../data.h5ad" />
							</div>
							<div className="grid md:grid-cols-3 gap-4">
								<div className="grid gap-2">
									<Label>Model</Label>
									<Input value={form.modelName} onChange={(e) => setForm({ ...form, modelName: e.target.value })} />
								</div>
								<div className="grid gap-2">
									<Label>Num Analyses</Label>
									<Input type="number" value={form.numAnalyses} onChange={(e) => setForm({ ...form, numAnalyses: Number(e.target.value) })} />
								</div>
								<div className="grid gap-2">
									<Label>Max Iterations</Label>
									<Input type="number" value={form.maxIterations} onChange={(e) => setForm({ ...form, maxIterations: Number(e.target.value) })} />
								</div>
							</div>
							<Button onClick={onSubmitProvider} disabled={!isConnected}>Submit</Button>
						</CardContent>
					</Card>
				</TabsContent>
				<TabsContent value="donor">
					<Card>
						<CardHeader>
							<CardTitle>Donate</CardTitle>
						</CardHeader>
						<CardContent className="space-y-4">
							<div className="grid md:grid-cols-3 gap-4">
								<div className="grid gap-2">
									<Label>ERC20 Token Address</Label>
									<Input value={DONATION_TOKEN_ADDR} readOnly />
								</div>
								<div className="grid gap-2">
									<Label>Amount</Label>
									<Input value={donation.amount} onChange={(e) => setDonation({ ...donation, amount: e.target.value })} placeholder="e.g., 100.5" />
								</div>
								<div className="grid gap-2 items-end">
									<Button onClick={onDonate} disabled={!isConnected}>Donate</Button>
								</div>
							</div>
							<div className="space-y-2">
								<h3 className="font-medium">Queue</h3>
								{queueLoading ? (
									<div className="grid gap-2">
										<Skeleton className="h-24 w-full" />
										<Skeleton className="h-24 w-full" />
									</div>
								) : (
									<>
										<div className="grid gap-2">
											{queue?.filter((q: any) => !q.completed).map((q: any) => (
												<Card key={q.id}>
													<CardHeader>
														<CardTitle className="text-base flex items-center justify-between">
															<span>{q.analysisName}</span>
															<Button size="sm" onClick={() => vote(q.id)} disabled={!isConnected}>Vote</Button>
														</CardTitle>
													</CardHeader>
													<CardContent>
														<div className="text-sm text-muted-foreground">{q.description}</div>
														<div className="text-xs mt-2">Model: {q.modelName}</div>
														<div className="text-xs">Governance Votes: {formatUnits(q.priority, 18)}</div>
													</CardContent>
												</Card>
											))}
										</div>
										<div className="space-y-2 mt-6">
											<h4 className="font-medium">Completed</h4>
											<div className="grid gap-2">
												{queue?.filter((q: any) => q.completed).map((q: any) => (
													<Card key={q.id} className="opacity-60">
														<CardHeader>
															<CardTitle className="text-base flex items-center justify-between">
																<span>{q.analysisName}</span>
															</CardTitle>
														</CardHeader>
														<CardContent>
															<div className="text-sm text-muted-foreground">{q.description}</div>
															<div className="text-xs mt-2">Model: {q.modelName}</div>
														</CardContent>
													</Card>
												))}
											</div>
										</div>
									</>
								)}
							</div>
						</CardContent>
					</Card>
				</TabsContent>
			</Tabs>
    </div>
  );
}
