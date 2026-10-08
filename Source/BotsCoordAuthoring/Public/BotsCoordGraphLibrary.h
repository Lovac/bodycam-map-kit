// BotsCoord authoring tool: python-callable builders for Blueprint graphs and behaviour trees (editor only, never
// shipped). Every call returns nullptr/false on failure and leaves the reason in GetLastError(). Types are strings:
// bool int int64 float double name string text byte vector rotator transform, object:<class path>,
// class:<class path>, struct:<struct path>, enum:<enum path>, any of them + "[]" for an array.
#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "BotsCoordGraphLibrary.generated.h"

class UBlueprint;
class UEdGraph;
class UEdGraphNode;
class UBehaviorTree;

UCLASS()
class BOTSCOORDAUTHORING_API UBotsCoordGraphLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/** The reason the last call failed ("" when it succeeded). */
	UFUNCTION(BlueprintCallable, Category = "BotsCoord")
	static FString GetLastError();

	// ---------------------------------------------------------------- Blueprints
	/** Create /Game/... Blueprint with that parent, or load it and remove every graph node, function and variable. */
	UFUNCTION(BlueprintCallable, Category = "BotsCoord")
	static UBlueprint* CreateOrClearBlueprint(const FString& AssetPath, const FString& ParentClassPath);

	UFUNCTION(BlueprintCallable, Category = "BotsCoord")
	static bool AddMemberVariable(UBlueprint* Blueprint, const FString& Name, const FString& Type, const FString& DefaultValue,
	                              bool bInstanceEditable, bool bExposeOnSpawn);

	/** A function graph. Inputs/Outputs: "Name:type;Name2:type". Returns the graph. */
	UFUNCTION(BlueprintCallable, Category = "BotsCoord")
	static UEdGraph* AddFunction(UBlueprint* Blueprint, const FString& Name, const FString& Inputs, const FString& Outputs, bool bPure);

	UFUNCTION(BlueprintCallable, Category = "BotsCoord")
	static bool AddLocalVariable(UBlueprint* Blueprint, UEdGraph* Graph, const FString& Name, const FString& Type, const FString& DefaultValue);

	/** "EventGraph" or a function graph's name. */
	UFUNCTION(BlueprintCallable, Category = "BotsCoord")
	static UEdGraph* GetGraph(UBlueprint* Blueprint, const FString& Name);

	/** Compile; returns every message, one per line, prefixed "E: " (error) or "W: " (warning). */
	UFUNCTION(BlueprintCallable, Category = "BotsCoord")
	static FString Compile(UBlueprint* Blueprint);

	// ---------------------------------------------------------------- nodes
	/** Override of a parent event, e.g. ReceiveExecuteAI (BTTask_BlueprintBase), ReceiveBeginPlay (Actor). */
	UFUNCTION(BlueprintCallable, Category = "BotsCoord")
	static UEdGraphNode* AddEvent(UBlueprint* Blueprint, UEdGraph* Graph, const FString& EventName, int32 X, int32 Y);

	/** Function call. ClassPath "self" = a function of this Blueprint. */
	UFUNCTION(BlueprintCallable, Category = "BotsCoord")
	static UEdGraphNode* AddCall(UBlueprint* Blueprint, UEdGraph* Graph, const FString& ClassPath, const FString& FunctionName, int32 X, int32 Y);

	/** Variable get/set. ClassPath "self" = a member or local variable of this Blueprint, else a property of that class. */
	UFUNCTION(BlueprintCallable, Category = "BotsCoord")
	static UEdGraphNode* AddVariable(UBlueprint* Blueprint, UEdGraph* Graph, const FString& ClassPath, const FString& VariableName, bool bSet, int32 X, int32 Y);

	UFUNCTION(BlueprintCallable, Category = "BotsCoord")
	static UEdGraphNode* AddCast(UBlueprint* Blueprint, UEdGraph* Graph, const FString& ClassPath, bool bPure, int32 X, int32 Y);

	/** Kind: Branch, Sequence (Count outputs), Self, MakeArray (Count inputs), Entry, Return (the function's nodes). */
	UFUNCTION(BlueprintCallable, Category = "BotsCoord")
	static UEdGraphNode* AddSimple(UBlueprint* Blueprint, UEdGraph* Graph, const FString& Kind, int32 Count, int32 X, int32 Y);

	/** A StandardMacros macro: ForEachLoop, ForLoop, IsValid, WhileLoop, DoOnce, Gate, ... */
	UFUNCTION(BlueprintCallable, Category = "BotsCoord")
	static UEdGraphNode* AddMacro(UBlueprint* Blueprint, UEdGraph* Graph, const FString& MacroName, int32 X, int32 Y);

	UFUNCTION(BlueprintCallable, Category = "BotsCoord")
	static UEdGraphNode* AddSpawnActor(UBlueprint* Blueprint, UEdGraph* Graph, const FString& ClassPath, int32 X, int32 Y);

	/** Link A.PinA (output) to B.PinB (input) through the K2 schema (types checked, wildcards resolved). */
	UFUNCTION(BlueprintCallable, Category = "BotsCoord")
	static bool Connect(UEdGraphNode* A, const FString& PinA, UEdGraphNode* B, const FString& PinB);

	/** Literal on an input pin; an object/class pin takes an object path. */
	UFUNCTION(BlueprintCallable, Category = "BotsCoord")
	static bool SetPinDefault(UEdGraphNode* Node, const FString& Pin, const FString& Value);

	/** "dir name type" per pin, for writing specs. */
	UFUNCTION(BlueprintCallable, Category = "BotsCoord")
	static FString ListPins(UEdGraphNode* Node);

	// ---------------------------------------------------------------- behaviour trees
	UFUNCTION(BlueprintCallable, Category = "BotsCoord")
	static UBehaviorTree* CreateOrLoadBehaviorTree(const FString& AssetPath);

	/** Replace the tree's runtime nodes from a JSON spec (see Scripts/bots/coord/README.md). The editor graph is dropped:
	 *  these trees are generated; never edit them in the Behavior Tree editor. */
	UFUNCTION(BlueprintCallable, Category = "BotsCoord")
	static bool BuildBehaviorTree(UBehaviorTree* Tree, const FString& JsonSpec);

	UFUNCTION(BlueprintCallable, Category = "BotsCoord")
	static FString DescribeBehaviorTree(UBehaviorTree* Tree);
};
