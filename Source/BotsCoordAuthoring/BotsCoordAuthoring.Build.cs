// BotsCoord authoring tool (26 Sep 2026, Lovac: "build the tool first"): an EDITOR-ONLY module that lets python build
// Blueprint graphs node by node (pins are created by the nodes themselves, links go through the K2 schema) and build
// behaviour trees from a JSON spec, so the bot logic for Bodycam (Saved/bots/COORD_DESIGN.md) is generated, not clicked.
// Nothing in this module is ever cooked or shipped; the assets it creates reference engine classes only.
using UnrealBuildTool;

public class BotsCoordAuthoring : ModuleRules
{
	public BotsCoordAuthoring(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine" });
		PrivateDependencyModuleNames.AddRange(new string[] {
			"UnrealEd", "BlueprintGraph", "Kismet", "KismetCompiler", "AIModule", "GameplayTasks",
			"AssetRegistry", "Json", "JsonUtilities", "Slate", "SlateCore" });
	}
}
