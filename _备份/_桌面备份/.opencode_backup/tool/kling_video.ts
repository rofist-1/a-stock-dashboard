import { tool } from "@opencode-ai/plugin";

const BASE = "https://api.klingai.com/v1";

export default tool({
  description: "Generate video using Kling AI (可灵AI)",
  args: {
    prompt: tool.schema.string().describe("Video description, max 2500 chars"),
    image_url: tool.schema.string().optional().describe("Image URL for image-to-video"),
    duration: tool.schema.number().optional().describe("Duration: 5 or 10 seconds"),
    aspect_ratio: tool.schema.string().optional().describe("16:9, 9:16, 1:1"),
    model: tool.schema.string().optional().describe("Model: kling-v2.6-pro (default), kling-v2.5-turbo, kling-video-o1"),
    mode: tool.schema.string().optional().describe("standard (default) or professional"),
    negative_prompt: tool.schema.string().optional().describe("What to avoid in the video"),
  },
  async execute(args, ctx) {
    const token = process.env.KLING_API_KEY;
    if (!token) throw new Error("Set KLING_API_KEY env var first");

    const endpoint = args.image_url ? "/videos/image2video" : "/videos/text2video";
    const body: Record<string, any> = {
      model: args.model ?? "kling-v2.6-pro",
      prompt: args.prompt,
      duration: args.duration ?? 5,
      aspect_ratio: args.aspect_ratio ?? "16:9",
      mode: args.mode ?? "standard",
    };
    if (args.image_url) body.image_url = args.image_url;
    if (args.negative_prompt) body.negative_prompt = args.negative_prompt;

    const res = await fetch(`${BASE}${endpoint}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`);
    const { data } = await res.json();
    const taskId = data.task_id;

    while (true) {
      const poll = await fetch(`${BASE}/videos/${endpoint.split("/")[2]}/${taskId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const result = await poll.json();
      const status = result.data.task_status;
      if (status === "succeed") {
        const videos = result.data.task_result?.videos || [];
        return videos.map((v: any) => v.url).join("\n") || "Video generated, but no URL returned";
      }
      if (status === "failed") throw new Error(`Generation failed: ${result.data.task_status_msg || "unknown"}`);
      await new Promise(r => setTimeout(r, 5000));
    }
  },
});
