export {};

declare module "agora-rtm-sdk" {
  namespace RTMEvents {
    interface RTMClientEventMap {
      status: (event: { state?: string; reason?: string }) => void;
    }
  }
}
