"use client";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { useState, useMemo } from "react";
import { useAccount, useChainId, useWriteContract, useReadContract } from "wagmi";
import { useQuery } from "@tanstack/react-query";

const governanceAbi = [
	{
		type: "function",
		name: "addResearch",
		stateMutability: "nonpayable",
		inputs: [
			{ name: "analysisName", type: "string" },
			{ name: "description", type: "string" },
			{ name: "encryptedH5adPath", type: "string" },
			{ name: "modelName", type: "string" },
			{ name: "numAnalyses", type: "uint32" },
			{ name: "maxIterations", type: "uint32" },
		],
		outputs: [{ name: "id", type: "uint256" }],
	},
	{ type: "function", name: "researchCount", stateMutability: "view", inputs: [], outputs: [{ type: "uint256" }] },
	{
		type: "function",
		name: "getResearch",
		stateMutability: "view",
		inputs: [{ name: "id", type: "uint256" }],
		outputs: [
			{
				type: "tuple",
				components: [
					{ name: "analysisName", type: "string" },
					{ name: "description", type: "string" },
					{ name: "encryptedH5adPath", type: "string" },
					{ name: "modelName", type: "string" },
					{ name: "numAnalyses", type: "uint32" },
					{ name: "maxIterations", type: "uint32" },
					{ name: "submitter", type: "address" },
					{ name: "createdAt", type: "uint64" },
					{ name: "priority", type: "uint256" },
					{ name: "totalVotes", type: "uint256" },
				],
			},
		],
	},
	{ type: "function", name: "bumpPriority", stateMutability: "nonpayable", inputs: [{ name: "id", type: "uint256" }], outputs: [] },
];

const erc20Abi = [
	{ type: "function", name: "approve", stateMutability: "nonpayable", inputs: [{ name: "spender", type: "address" }, { name: "value", type: "uint256" }], outputs: [{ type: "bool" }] },
	{ type: "function", name: "allowance", stateMutability: "view", inputs: [{ name: "owner", type: "address" }, { name: "spender", type: "address" }], outputs: [{ type: "uint256" }] },
	{ type: "function", name: "balanceOf", stateMutability: "view", inputs: [{ name: "account", type: "address" }], outputs: [{ type: "uint256" }] },
	{ type: "function", name: "decimals", stateMutability: "view", inputs: [], outputs: [{ type: "uint8" }] },
];

const donationAbi = [
	{ type: "function", name: "setWhitelist", stateMutability: "nonpayable", inputs: [{ name: "token", type: "address" }, { name: "allowed", type: "bool" }, { name: "rate", type: "uint256" }], outputs: [] },
	{ type: "function", name: "donate", stateMutability: "nonpayable", inputs: [{ name: "token", type: "address" }, { name: "amount", type: "uint256" }], outputs: [] },
	{ type: "function", name: "balanceOf", stateMutability: "view", inputs: [{ name: "account", type: "address" }], outputs: [{ type: "uint256" }] },
];

const GOV_ADDR = process.env.NEXT_PUBLIC_GOV_ADDRESS as `0x${string}` | undefined;
const SBT_ADDR = process.env.NEXT_PUBLIC_SBT_ADDRESS as `0x${string}` | undefined;

export default function Home() {
	const [tab, setTab] = useState("provider");
	const { isConnected } = useAccount();
	const { writeContractAsync } = useWriteContract();

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
		await writeContractAsync({
			abi: governanceAbi as any,
			address: GOV_ADDR,
			functionName: "addResearch",
			args: [
				form.analysisName,
				form.description,
				form.datasetUrl,
				form.modelName,
				BigInt(form.numAnalyses),
				BigInt(form.maxIterations),
			],
		});
		setForm({ analysisName: "", description: "", datasetUrl: "", modelName: "o3-mini", numAnalyses: 1, maxIterations: 3 });
	}

	const [donation, setDonation] = useState({ token: "", amount: "" });
	async function onDonate() {
		if (!SBT_ADDR) return alert("Missing NEXT_PUBLIC_SBT_ADDRESS");
		const amount = BigInt(donation.amount || "0");
		await writeContractAsync({ abi: erc20Abi as any, address: donation.token as any, functionName: "approve", args: [SBT_ADDR, amount] });
		await writeContractAsync({ abi: donationAbi as any, address: SBT_ADDR, functionName: "donate", args: [donation.token as any, amount] });
	}

	const { data: count } = useReadContract({ abi: governanceAbi as any, address: GOV_ADDR, functionName: "researchCount", args: [] });
	const items = useMemo(() => Number(count || 0), [count]);

	const { data: queue } = useQuery({
		queryKey: ["queue", items, GOV_ADDR],
		queryFn: async () => {
			if (!GOV_ADDR) return [] as any[];
			const client = (window as any).wagmi?.getClient?.();
			if (!client) return [] as any[];
			const calls = Array.from({ length: items }).map((_, i) => client.readContract({ address: GOV_ADDR, abi: governanceAbi, functionName: "getResearch", args: [BigInt(i)] }));
			const all = await Promise.all(calls);
			return all.map((r: any, i: number) => ({ id: i, analysisName: r[0], description: r[1], modelName: r[3], priority: r[8] }));
		},
		enabled: !!GOV_ADDR && items > 0,
	});

	async function vote(id: number) {
		if (!GOV_ADDR) return;
		await writeContractAsync({ abi: governanceAbi as any, address: GOV_ADDR, functionName: "bumpPriority", args: [BigInt(id)] });
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
									<Input value={donation.token} onChange={(e) => setDonation({ ...donation, token: e.target.value })} />
								</div>
								<div className="grid gap-2">
									<Label>Amount (wei)</Label>
									<Input value={donation.amount} onChange={(e) => setDonation({ ...donation, amount: e.target.value })} />
								</div>
								<div className="grid gap-2 items-end">
									<Button onClick={onDonate} disabled={!isConnected}>Donate</Button>
								</div>
							</div>
							<div className="space-y-2">
								<h3 className="font-medium">Queue</h3>
								<div className="grid gap-2">
									{queue?.map((q: any) => (
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
												<div className="text-xs">Priority: {q.priority?.toString?.() ?? String(q.priority)}</div>
											</CardContent>
										</Card>
									))}
								</div>
							</div>
						</CardContent>
					</Card>
				</TabsContent>
			</Tabs>
		</div>
	);
}
