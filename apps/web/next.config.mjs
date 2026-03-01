/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",

  /**
   * Proxy /api/* requests to the FastAPI backend.
   *
   * Docker:
   *   - set API_URL=http://api:8000 (service name)
   *   - if API_URL is missing, default to http://api:8000 (NEVER localhost)
   *
   * Local (non-docker):
   *   - default to http://127.0.0.1:8000 (avoid ::1)
   */
  async rewrites() {
    const apiUrl = process.env.API_URL;
    const isDocker = process.env.DOCKER === "1" || !!apiUrl; // docker compose will always provide API_URL

    const target = isDocker
      ? (apiUrl || "http://api:8000")
      : "http://127.0.0.1:8000";

    console.log(`[next.config] isDocker=${isDocker} API_URL=${apiUrl || "(unset)"} => proxy=${target}`);

    return [
      {
        source: "/api/:path*",
        destination: `${target}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;