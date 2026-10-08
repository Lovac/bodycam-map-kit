#include "BotsCoordGraphLibrary.h"

#include "AssetRegistry/AssetRegistryModule.h"
#include "BehaviorTree/BTCompositeNode.h"
#include "BehaviorTree/BTDecorator.h"
#include "BehaviorTree/BTService.h"
#include "BehaviorTree/BTTaskNode.h"
#include "BehaviorTree/BehaviorTree.h"
#include "BehaviorTree/BlackboardData.h"
#include "BehaviorTree/Composites/BTComposite_Selector.h"
#include "BehaviorTree/Composites/BTComposite_Sequence.h"
#include "Dom/JsonObject.h"
#include "EdGraph/EdGraph.h"
#include "EdGraphSchema_K2.h"
#include "Engine/Blueprint.h"
#include "Engine/BlueprintGeneratedClass.h"
#include "K2Node_CallArrayFunction.h"
#include "K2Node_CallFunction.h"
#include "K2Node_DynamicCast.h"
#include "K2Node_Event.h"
#include "K2Node_ExecutionSequence.h"
#include "K2Node_FunctionEntry.h"
#include "K2Node_FunctionResult.h"
#include "K2Node_IfThenElse.h"
#include "K2Node_MacroInstance.h"
#include "K2Node_MakeArray.h"
#include "K2Node_Self.h"
#include "K2Node_SpawnActorFromClass.h"
#include "K2Node_VariableGet.h"
#include "K2Node_VariableSet.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/CompilerResultsLog.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "UObject/Package.h"
#include "UObject/UObjectHash.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(BotsCoordGraphLibrary)

namespace
{
	FString GLastError;

	template <typename T>
	T* Fail(const FString& Msg)
	{
		GLastError = Msg;
		UE_LOG(LogTemp, Warning, TEXT("[botscoord] %s"), *Msg);
		return nullptr;
	}

	bool FailB(const FString& Msg)
	{
		Fail<UObject>(Msg);
		return false;
	}

	void Ok() { GLastError.Reset(); }

	UClass* LoadClassPath(const FString& Path)
	{
		UClass* C = LoadObject<UClass>(nullptr, *Path);
		if (!C)
		{
			C = FindFirstObject<UClass>(*Path, EFindFirstObjectOptions::ExactClass);
		}
		return C;
	}

	/** "bool", "object:/Script/Engine.Actor", "vector[]", ... -> pin type */
	bool ParseType(const FString& In, FEdGraphPinType& Out, FString& Err)
	{
		FString T = In.TrimStartAndEnd();
		const bool bArray = T.EndsWith(TEXT("[]"));
		if (bArray)
		{
			T.LeftChopInline(2);
		}
		Out = FEdGraphPinType();
		FString Kind = T, Arg;
		T.Split(TEXT(":"), &Kind, &Arg);
		if (!T.Contains(TEXT(":")))
		{
			Kind = T;
			Arg.Reset();
		}
		Kind = Kind.ToLower();
		if (Kind == TEXT("bool")) { Out.PinCategory = UEdGraphSchema_K2::PC_Boolean; }
		else if (Kind == TEXT("int")) { Out.PinCategory = UEdGraphSchema_K2::PC_Int; }
		else if (Kind == TEXT("int64")) { Out.PinCategory = UEdGraphSchema_K2::PC_Int64; }
		else if (Kind == TEXT("float")) { Out.PinCategory = UEdGraphSchema_K2::PC_Real; Out.PinSubCategory = UEdGraphSchema_K2::PC_Float; }
		else if (Kind == TEXT("double") || Kind == TEXT("real")) { Out.PinCategory = UEdGraphSchema_K2::PC_Real; Out.PinSubCategory = UEdGraphSchema_K2::PC_Double; }
		else if (Kind == TEXT("name")) { Out.PinCategory = UEdGraphSchema_K2::PC_Name; }
		else if (Kind == TEXT("string")) { Out.PinCategory = UEdGraphSchema_K2::PC_String; }
		else if (Kind == TEXT("text")) { Out.PinCategory = UEdGraphSchema_K2::PC_Text; }
		else if (Kind == TEXT("byte")) { Out.PinCategory = UEdGraphSchema_K2::PC_Byte; }
		else if (Kind == TEXT("vector")) { Out.PinCategory = UEdGraphSchema_K2::PC_Struct; Out.PinSubCategoryObject = TBaseStructure<FVector>::Get(); }
		else if (Kind == TEXT("rotator")) { Out.PinCategory = UEdGraphSchema_K2::PC_Struct; Out.PinSubCategoryObject = TBaseStructure<FRotator>::Get(); }
		else if (Kind == TEXT("transform")) { Out.PinCategory = UEdGraphSchema_K2::PC_Struct; Out.PinSubCategoryObject = TBaseStructure<FTransform>::Get(); }
		else if (Kind == TEXT("object") || Kind == TEXT("class"))
		{
			UClass* C = LoadClassPath(Arg);
			if (!C) { Err = FString::Printf(TEXT("type %s: class '%s' not found"), *In, *Arg); return false; }
			Out.PinCategory = Kind == TEXT("object") ? UEdGraphSchema_K2::PC_Object : UEdGraphSchema_K2::PC_Class;
			Out.PinSubCategoryObject = C;
		}
		else if (Kind == TEXT("struct"))
		{
			UScriptStruct* S = LoadObject<UScriptStruct>(nullptr, *Arg);
			if (!S) { Err = FString::Printf(TEXT("type %s: struct '%s' not found"), *In, *Arg); return false; }
			Out.PinCategory = UEdGraphSchema_K2::PC_Struct;
			Out.PinSubCategoryObject = S;
		}
		else if (Kind == TEXT("enum"))
		{
			UEnum* E = LoadObject<UEnum>(nullptr, *Arg);
			if (!E) { Err = FString::Printf(TEXT("type %s: enum '%s' not found"), *In, *Arg); return false; }
			Out.PinCategory = UEdGraphSchema_K2::PC_Byte;
			Out.PinSubCategoryObject = E;
		}
		else
		{
			Err = FString::Printf(TEXT("unknown type '%s'"), *In);
			return false;
		}
		if (bArray)
		{
			Out.ContainerType = EPinContainerType::Array;
		}
		return true;
	}

	template <typename NodeT>
	NodeT* Place(UEdGraph* Graph, int32 X, int32 Y, TFunctionRef<void(NodeT*)> Configure)
	{
		FGraphNodeCreator<NodeT> Creator(*Graph);
		NodeT* N = Creator.CreateNode(false);
		N->NodePosX = X;
		N->NodePosY = Y;
		Configure(N);
		Creator.Finalize();
		return N;
	}

	UEdGraphPin* FindPinIn(UEdGraphNode* Node, const FString& Name, EEdGraphPinDirection Preferred)
	{
		if (!Node)
		{
			return nullptr;
		}
		if (UEdGraphPin* P = Node->FindPin(FName(*Name), Preferred))
		{
			return P;
		}
		for (UEdGraphPin* P : Node->Pins)   // case-insensitive name, then display name
		{
			if (P && P->Direction == Preferred && P->PinName.ToString().Equals(Name, ESearchCase::IgnoreCase))
			{
				return P;
			}
		}
		for (UEdGraphPin* P : Node->Pins)
		{
			if (P && P->Direction == Preferred && P->PinFriendlyName.ToString().Equals(Name, ESearchCase::IgnoreCase))
			{
				return P;
			}
		}
		return Node->FindPin(FName(*Name));
	}

	FString PinList(UEdGraphNode* Node)
	{
		TArray<FString> L;
		for (UEdGraphPin* P : Node->Pins)
		{
			if (P && !P->bHidden)
			{
				L.Add(FString::Printf(TEXT("%s %s %s"), P->Direction == EGPD_Input ? TEXT("in") : TEXT("out"), *P->PinName.ToString(),
				                      *UEdGraphSchema_K2::TypeToText(P->PinType).ToString()));
			}
		}
		return FString::Join(L, TEXT(" | "));
	}

	UK2Node_FunctionEntry* EntryOf(UEdGraph* Graph)
	{
		for (UEdGraphNode* N : Graph->Nodes)
		{
			if (UK2Node_FunctionEntry* E = Cast<UK2Node_FunctionEntry>(N))
			{
				return E;
			}
		}
		return nullptr;
	}

	/** name1:type1;name2:type2 -> pins on an editable node */
	bool AddParams(UK2Node_EditablePinBase* Node, const FString& Spec, EEdGraphPinDirection Dir, FString& Err)
	{
		TArray<FString> Items;
		Spec.ParseIntoArray(Items, TEXT(";"), true);
		for (const FString& It : Items)
		{
			FString N, T;
			if (!It.Split(TEXT(":"), &N, &T))
			{
				Err = FString::Printf(TEXT("parameter '%s' is not name:type"), *It);
				return false;
			}
			FEdGraphPinType PT;
			if (!ParseType(T, PT, Err))
			{
				return false;
			}
			if (!Node->CreateUserDefinedPin(FName(*N.TrimStartAndEnd()), PT, Dir, false))
			{
				Err = FString::Printf(TEXT("could not add parameter '%s'"), *It);
				return false;
			}
		}
		return true;
	}
}

FString UBotsCoordGraphLibrary::GetLastError()
{
	return GLastError;
}

UBlueprint* UBotsCoordGraphLibrary::CreateOrClearBlueprint(const FString& AssetPath, const FString& ParentClassPath)
{
	UClass* Parent = LoadClassPath(ParentClassPath);
	if (!Parent)
	{
		return Fail<UBlueprint>(FString::Printf(TEXT("parent class '%s' not found"), *ParentClassPath));
	}
	const FString AssetName = FPackageName::GetLongPackageAssetName(AssetPath);
	UBlueprint* BP = LoadObject<UBlueprint>(nullptr, *(AssetPath + TEXT(".") + AssetName), nullptr, LOAD_NoWarn | LOAD_Quiet);
	if (BP && BP->ParentClass != Parent)
	{
		return Fail<UBlueprint>(FString::Printf(TEXT("%s exists with parent %s, not %s"), *AssetPath, *GetNameSafe(BP->ParentClass), *Parent->GetName()));
	}
	if (!BP)
	{
		UPackage* Pkg = CreatePackage(*AssetPath);
		const EBlueprintType Type = Parent->IsChildOf(UBlueprintFunctionLibrary::StaticClass()) ? BPTYPE_FunctionLibrary : BPTYPE_Normal;
		BP = FKismetEditorUtilities::CreateBlueprint(Parent, Pkg, FName(*AssetName), Type, UBlueprint::StaticClass(),
		                                             UBlueprintGeneratedClass::StaticClass(), FName(TEXT("BotsCoord")));
		if (!BP)
		{
			return Fail<UBlueprint>(FString::Printf(TEXT("could not create %s"), *AssetPath));
		}
		FAssetRegistryModule::AssetCreated(BP);
	}
	// clear: every function graph, every event-graph node (including the ghost default events), every variable
	TArray<UEdGraph*> Functions = BP->FunctionGraphs;
	if (Functions.Num())
	{
		FBlueprintEditorUtils::RemoveGraphs(BP, Functions);
	}
	for (UEdGraph* Page : BP->UbergraphPages)
	{
		TArray<UEdGraphNode*> Nodes = Page->Nodes;
		for (UEdGraphNode* N : Nodes)
		{
			FBlueprintEditorUtils::RemoveNode(BP, N, true);
		}
	}
	TArray<FName> Vars;
	for (const FBPVariableDescription& V : BP->NewVariables)
	{
		Vars.Add(V.VarName);
	}
	if (Vars.Num())
	{
		FBlueprintEditorUtils::BulkRemoveMemberVariables(BP, Vars);
	}
	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP);
	BP->MarkPackageDirty();
	Ok();
	return BP;
}

bool UBotsCoordGraphLibrary::AddMemberVariable(UBlueprint* Blueprint, const FString& Name, const FString& Type, const FString& DefaultValue,
                                               bool bInstanceEditable, bool bExposeOnSpawn)
{
	if (!Blueprint) return FailB(TEXT("AddMemberVariable: no blueprint"));
	FEdGraphPinType PT;
	FString Err;
	if (!ParseType(Type, PT, Err)) return FailB(Err);
	if (!FBlueprintEditorUtils::AddMemberVariable(Blueprint, FName(*Name), PT, DefaultValue))
	{
		return FailB(FString::Printf(TEXT("could not add variable %s (name taken?)"), *Name));
	}
	FBlueprintEditorUtils::SetBlueprintOnlyEditableFlag(Blueprint, FName(*Name), !bInstanceEditable);
	if (bExposeOnSpawn)
	{
		FBlueprintEditorUtils::SetBlueprintVariableMetaData(Blueprint, FName(*Name), nullptr, FBlueprintMetadata::MD_ExposeOnSpawn, TEXT("true"));
	}
	Ok();
	return true;
}

UEdGraph* UBotsCoordGraphLibrary::AddFunction(UBlueprint* Blueprint, const FString& Name, const FString& Inputs, const FString& Outputs, bool bPure)
{
	if (!Blueprint) return Fail<UEdGraph>(TEXT("AddFunction: no blueprint"));
	UEdGraph* G = FBlueprintEditorUtils::CreateNewGraph(Blueprint, FName(*Name), UEdGraph::StaticClass(), UEdGraphSchema_K2::StaticClass());
	FBlueprintEditorUtils::AddFunctionGraph<UClass>(Blueprint, G, true, nullptr);
	UK2Node_FunctionEntry* Entry = EntryOf(G);
	if (!Entry) return Fail<UEdGraph>(FString::Printf(TEXT("function %s has no entry node"), *Name));
	FString Err;
	if (!AddParams(Entry, Inputs, EGPD_Output, Err)) return Fail<UEdGraph>(FString::Printf(TEXT("%s inputs: %s"), *Name, *Err));
	if (!Outputs.IsEmpty())
	{
		UK2Node_FunctionResult* Result = FBlueprintEditorUtils::FindOrCreateFunctionResultNode(Entry);
		if (!Result) return Fail<UEdGraph>(FString::Printf(TEXT("function %s: no result node"), *Name));
		Result->NodePosX = Entry->NodePosX + 1600;
		Result->NodePosY = Entry->NodePosY;
		if (!AddParams(Result, Outputs, EGPD_Input, Err)) return Fail<UEdGraph>(FString::Printf(TEXT("%s outputs: %s"), *Name, *Err));
	}
	if (bPure)
	{
		Entry->AddExtraFlags(FUNC_BlueprintPure);
	}
	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
	Ok();
	return G;
}

bool UBotsCoordGraphLibrary::AddLocalVariable(UBlueprint* Blueprint, UEdGraph* Graph, const FString& Name, const FString& Type, const FString& DefaultValue)
{
	if (!Blueprint || !Graph) return FailB(TEXT("AddLocalVariable: no blueprint/graph"));
	FEdGraphPinType PT;
	FString Err;
	if (!ParseType(Type, PT, Err)) return FailB(Err);
	if (!FBlueprintEditorUtils::AddLocalVariable(Blueprint, Graph, FName(*Name), PT, DefaultValue))
	{
		return FailB(FString::Printf(TEXT("could not add local %s to %s"), *Name, *Graph->GetName()));
	}
	Ok();
	return true;
}

UEdGraph* UBotsCoordGraphLibrary::GetGraph(UBlueprint* Blueprint, const FString& Name)
{
	if (!Blueprint) return Fail<UEdGraph>(TEXT("GetGraph: no blueprint"));
	if (Name == TEXT("EventGraph"))
	{
		if (UEdGraph* G = FBlueprintEditorUtils::FindEventGraph(Blueprint))
		{
			Ok();
			return G;
		}
		return Fail<UEdGraph>(TEXT("no event graph"));
	}
	for (UEdGraph* G : Blueprint->FunctionGraphs)
	{
		if (G && G->GetName() == Name)
		{
			Ok();
			return G;
		}
	}
	return Fail<UEdGraph>(FString::Printf(TEXT("graph %s not found"), *Name));
}

FString UBotsCoordGraphLibrary::Compile(UBlueprint* Blueprint)
{
	if (!Blueprint) return TEXT("E: no blueprint");
	FCompilerResultsLog Log;
	Log.bSilentMode = true;
	FKismetEditorUtilities::CompileBlueprint(Blueprint, EBlueprintCompileOptions::SkipGarbageCollection, &Log);
	TArray<FString> Lines;
	for (const TSharedRef<FTokenizedMessage>& M : Log.Messages)
	{
		const EMessageSeverity::Type S = M->GetSeverity();
		if (S == EMessageSeverity::Error || S == EMessageSeverity::Warning || S == EMessageSeverity::PerformanceWarning)
		{
			Lines.Add(FString::Printf(TEXT("%s: %s"), S == EMessageSeverity::Error ? TEXT("E") : TEXT("W"), *M->ToText().ToString()));
		}
	}
	if (Blueprint->Status == BS_Error && !Lines.ContainsByPredicate([](const FString& L) { return L.StartsWith(TEXT("E:")); }))
	{
		Lines.Add(TEXT("E: blueprint status is Error"));
	}
	Ok();
	return FString::Join(Lines, TEXT("\n"));
}

UEdGraphNode* UBotsCoordGraphLibrary::AddEvent(UBlueprint* Blueprint, UEdGraph* Graph, const FString& EventName, int32 X, int32 Y)
{
	if (!Blueprint || !Graph) return Fail<UEdGraphNode>(TEXT("AddEvent: no blueprint/graph"));
	UFunction* F = Blueprint->ParentClass ? Blueprint->ParentClass->FindFunctionByName(FName(*EventName)) : nullptr;
	if (!F) return Fail<UEdGraphNode>(FString::Printf(TEXT("event %s not found on %s"), *EventName, *GetNameSafe(Blueprint->ParentClass)));
	UClass* Owner = F->GetOwnerClass();
	if (UK2Node_Event* Existing = FBlueprintEditorUtils::FindOverrideForFunction(Blueprint, Owner, F->GetFName()))
	{
		Ok();
		return Existing;
	}
	UK2Node_Event* N = Place<UK2Node_Event>(Graph, X, Y, [&](UK2Node_Event* E) {
		E->EventReference.SetExternalMember(F->GetFName(), Owner);
		E->bOverrideFunction = true;
	});
	Ok();
	return N;
}

UEdGraphNode* UBotsCoordGraphLibrary::AddCall(UBlueprint* Blueprint, UEdGraph* Graph, const FString& ClassPath, const FString& FunctionName, int32 X, int32 Y)
{
	if (!Blueprint || !Graph) return Fail<UEdGraphNode>(TEXT("AddCall: no blueprint/graph"));
	UClass* C = nullptr;
	if (ClassPath == TEXT("self"))
	{
		C = Blueprint->SkeletonGeneratedClass ? Blueprint->SkeletonGeneratedClass : Blueprint->GeneratedClass;
	}
	else
	{
		C = LoadClassPath(ClassPath);
	}
	if (!C) return Fail<UEdGraphNode>(FString::Printf(TEXT("class %s not found"), *ClassPath));
	UFunction* F = C->FindFunctionByName(FName(*FunctionName));
	if (!F) return Fail<UEdGraphNode>(FString::Printf(TEXT("function %s not found on %s"), *FunctionName, *C->GetName()));
	// wildcard array functions (Array_Add, Array_Find...) need the array node, which propagates the pin types
	UEdGraphNode* N = nullptr;
	if (F->HasMetaData(FBlueprintMetadata::MD_ArrayParam))
	{
		N = Place<UK2Node_CallArrayFunction>(Graph, X, Y, [&](UK2Node_CallArrayFunction* K) { K->SetFromFunction(F); });
	}
	else
	{
		N = Place<UK2Node_CallFunction>(Graph, X, Y, [&](UK2Node_CallFunction* K) { K->SetFromFunction(F); });
	}
	Ok();
	return N;
}

UEdGraphNode* UBotsCoordGraphLibrary::AddVariable(UBlueprint* Blueprint, UEdGraph* Graph, const FString& ClassPath, const FString& VariableName,
                                                  bool bSet, int32 X, int32 Y)
{
	if (!Blueprint || !Graph) return Fail<UEdGraphNode>(TEXT("AddVariable: no blueprint/graph"));
	const FName VN(*VariableName);
	TFunction<void(UK2Node_Variable*)> Configure;
	if (ClassPath == TEXT("self"))
	{
		if (FBPVariableDescription* L = FBlueprintEditorUtils::FindLocalVariable(Blueprint, Graph, VN))
		{
			const FGuid G = L->VarGuid;
			const FString Scope = Graph->GetName();
			Configure = [VN, G, Scope](UK2Node_Variable* V) { V->VariableReference.SetLocalMember(VN, Scope, G); };
		}
		else
		{
			const FGuid G = FBlueprintEditorUtils::FindMemberVariableGuidByName(Blueprint, VN);
			if (G.IsValid())
			{
				Configure = [VN, G](UK2Node_Variable* V) { V->VariableReference.SetSelfMember(VN, G); };
			}
			else
			{
				FProperty* P = Blueprint->ParentClass ? FindFProperty<FProperty>(Blueprint->ParentClass, VN) : nullptr;
				if (!P) return Fail<UEdGraphNode>(FString::Printf(TEXT("variable %s not found on %s"), *VariableName, *Blueprint->GetName()));
				Configure = [P](UK2Node_Variable* V) { V->VariableReference.SetFromField<FProperty>(P, true); };
			}
		}
	}
	else
	{
		UClass* C = LoadClassPath(ClassPath);
		FProperty* P = C ? FindFProperty<FProperty>(C, VN) : nullptr;
		if (!P) return Fail<UEdGraphNode>(FString::Printf(TEXT("property %s not found on %s"), *VariableName, *ClassPath));
		Configure = [P](UK2Node_Variable* V) { V->VariableReference.SetFromField<FProperty>(P, false); };
	}
	UEdGraphNode* N = nullptr;
	if (bSet)
	{
		N = Place<UK2Node_VariableSet>(Graph, X, Y, [&](UK2Node_VariableSet* V) { Configure(V); });
	}
	else
	{
		N = Place<UK2Node_VariableGet>(Graph, X, Y, [&](UK2Node_VariableGet* V) { Configure(V); });
	}
	Ok();
	return N;
}

UEdGraphNode* UBotsCoordGraphLibrary::AddCast(UBlueprint* Blueprint, UEdGraph* Graph, const FString& ClassPath, bool bPure, int32 X, int32 Y)
{
	if (!Blueprint || !Graph) return Fail<UEdGraphNode>(TEXT("AddCast: no blueprint/graph"));
	UClass* C = LoadClassPath(ClassPath);
	if (!C) return Fail<UEdGraphNode>(FString::Printf(TEXT("class %s not found"), *ClassPath));
	UK2Node_DynamicCast* N = Place<UK2Node_DynamicCast>(Graph, X, Y, [&](UK2Node_DynamicCast* K) {
		K->TargetType = C;
		K->SetPurity(bPure);
	});
	Ok();
	return N;
}

UEdGraphNode* UBotsCoordGraphLibrary::AddSimple(UBlueprint* Blueprint, UEdGraph* Graph, const FString& Kind, int32 Count, int32 X, int32 Y)
{
	if (!Blueprint || !Graph) return Fail<UEdGraphNode>(TEXT("AddSimple: no blueprint/graph"));
	UEdGraphNode* N = nullptr;
	if (Kind == TEXT("Branch"))
	{
		N = Place<UK2Node_IfThenElse>(Graph, X, Y, [](UK2Node_IfThenElse*) {});
	}
	else if (Kind == TEXT("Sequence"))
	{
		UK2Node_ExecutionSequence* S = Place<UK2Node_ExecutionSequence>(Graph, X, Y, [](UK2Node_ExecutionSequence*) {});
		for (int32 i = 2; i < Count; ++i)
		{
			S->AddInputPin();
		}
		N = S;
	}
	else if (Kind == TEXT("Self"))
	{
		N = Place<UK2Node_Self>(Graph, X, Y, [](UK2Node_Self*) {});
	}
	else if (Kind == TEXT("MakeArray"))
	{
		UK2Node_MakeArray* M = Place<UK2Node_MakeArray>(Graph, X, Y, [](UK2Node_MakeArray*) {});
		for (int32 i = 1; i < Count; ++i)
		{
			M->AddInputPin();
		}
		N = M;
	}
	else if (Kind == TEXT("Entry"))
	{
		N = EntryOf(Graph);
	}
	else if (Kind == TEXT("Return"))
	{
		for (UEdGraphNode* G : Graph->Nodes)
		{
			if (Cast<UK2Node_FunctionResult>(G))
			{
				N = G;
				break;
			}
		}
	}
	if (!N) return Fail<UEdGraphNode>(FString::Printf(TEXT("AddSimple: kind '%s' unknown or not present in %s"), *Kind, *Graph->GetName()));
	Ok();
	return N;
}

UEdGraphNode* UBotsCoordGraphLibrary::AddMacro(UBlueprint* Blueprint, UEdGraph* Graph, const FString& MacroName, int32 X, int32 Y)
{
	if (!Blueprint || !Graph) return Fail<UEdGraphNode>(TEXT("AddMacro: no blueprint/graph"));
	UBlueprint* Std = LoadObject<UBlueprint>(nullptr, TEXT("/Engine/EditorBlueprintResources/StandardMacros.StandardMacros"));
	if (!Std) return Fail<UEdGraphNode>(TEXT("StandardMacros not found"));
	UEdGraph* Macro = nullptr;
	for (UEdGraph* G : Std->MacroGraphs)
	{
		if (G && G->GetName() == MacroName)
		{
			Macro = G;
			break;
		}
	}
	if (!Macro) return Fail<UEdGraphNode>(FString::Printf(TEXT("macro %s not in StandardMacros"), *MacroName));
	UK2Node_MacroInstance* N = Place<UK2Node_MacroInstance>(Graph, X, Y, [&](UK2Node_MacroInstance* M) { M->SetMacroGraph(Macro); });
	Ok();
	return N;
}

UEdGraphNode* UBotsCoordGraphLibrary::AddSpawnActor(UBlueprint* Blueprint, UEdGraph* Graph, const FString& ClassPath, int32 X, int32 Y)
{
	if (!Blueprint || !Graph) return Fail<UEdGraphNode>(TEXT("AddSpawnActor: no blueprint/graph"));
	UClass* C = LoadClassPath(ClassPath);
	if (!C) return Fail<UEdGraphNode>(FString::Printf(TEXT("class %s not found"), *ClassPath));
	UK2Node_SpawnActorFromClass* N = Place<UK2Node_SpawnActorFromClass>(Graph, X, Y, [](UK2Node_SpawnActorFromClass*) {});
	UEdGraphPin* ClassPin = N->GetClassPin();
	if (!ClassPin) return Fail<UEdGraphNode>(TEXT("spawn node has no class pin"));
	GetDefault<UEdGraphSchema_K2>()->TrySetDefaultObject(*ClassPin, C);
	Ok();
	return N;
}

bool UBotsCoordGraphLibrary::Connect(UEdGraphNode* A, const FString& PinA, UEdGraphNode* B, const FString& PinB)
{
	if (!A || !B) return FailB(TEXT("Connect: missing node"));
	UEdGraphPin* PA = FindPinIn(A, PinA, EGPD_Output);
	UEdGraphPin* PB = FindPinIn(B, PinB, EGPD_Input);
	if (!PA) return FailB(FString::Printf(TEXT("pin '%s' not on %s [%s]"), *PinA, *A->GetNodeTitle(ENodeTitleType::ListView).ToString(), *PinList(A)));
	if (!PB) return FailB(FString::Printf(TEXT("pin '%s' not on %s [%s]"), *PinB, *B->GetNodeTitle(ENodeTitleType::ListView).ToString(), *PinList(B)));
	const UEdGraphSchema_K2* K2 = GetDefault<UEdGraphSchema_K2>();
	const FPinConnectionResponse R = K2->CanCreateConnection(PA, PB);
	if (R.Response == CONNECT_RESPONSE_DISALLOW)
	{
		return FailB(FString::Printf(TEXT("cannot link %s.%s -> %s.%s: %s"), *A->GetNodeTitle(ENodeTitleType::ListView).ToString(), *PinA,
		                             *B->GetNodeTitle(ENodeTitleType::ListView).ToString(), *PinB, *R.Message.ToString()));
	}
	if (!K2->TryCreateConnection(PA, PB))
	{
		return FailB(FString::Printf(TEXT("link %s -> %s refused"), *PinA, *PinB));
	}
	Ok();
	return true;
}

bool UBotsCoordGraphLibrary::SetPinDefault(UEdGraphNode* Node, const FString& Pin, const FString& Value)
{
	if (!Node) return FailB(TEXT("SetPinDefault: no node"));
	UEdGraphPin* P = FindPinIn(Node, Pin, EGPD_Input);
	if (!P) return FailB(FString::Printf(TEXT("input pin '%s' not on %s [%s]"), *Pin, *Node->GetNodeTitle(ENodeTitleType::ListView).ToString(), *PinList(Node)));
	const UEdGraphSchema_K2* K2 = GetDefault<UEdGraphSchema_K2>();
	const FName Cat = P->PinType.PinCategory;
	if (Cat == UEdGraphSchema_K2::PC_Object || Cat == UEdGraphSchema_K2::PC_Class || Cat == UEdGraphSchema_K2::PC_SoftObject ||
	    Cat == UEdGraphSchema_K2::PC_SoftClass)
	{
		UObject* O = Value.IsEmpty() ? nullptr : LoadObject<UObject>(nullptr, *Value);
		if (!Value.IsEmpty() && !O) return FailB(FString::Printf(TEXT("object %s not found for pin %s"), *Value, *Pin));
		K2->TrySetDefaultObject(*P, O);
	}
	else
	{
		K2->TrySetDefaultValue(*P, Value);
	}
	const FString Bad = K2->IsCurrentPinDefaultValid(P);
	if (!Bad.IsEmpty()) return FailB(FString::Printf(TEXT("pin %s default '%s': %s"), *Pin, *Value, *Bad));
	Ok();
	return true;
}

FString UBotsCoordGraphLibrary::ListPins(UEdGraphNode* Node)
{
	return Node ? PinList(Node) : FString();
}

// -------------------------------------------------------------------------------------------- behaviour trees
namespace
{
	bool ApplyProps(UObject* Obj, const TSharedPtr<FJsonObject>& Props, FString& Err)
	{
		if (!Props.IsValid())
		{
			return true;
		}
		for (const auto& KV : Props->Values)
		{
			FProperty* P = FindFProperty<FProperty>(Obj->GetClass(), FName(*KV.Key));
			if (!P)
			{
				Err = FString::Printf(TEXT("%s has no property %s"), *Obj->GetClass()->GetName(), *KV.Key);
				return false;
			}
			FString Text;
			if (!KV.Value->TryGetString(Text))
			{
				double D;
				bool B;
				if (KV.Value->TryGetNumber(D)) { Text = FString::SanitizeFloat(D); }
				else if (KV.Value->TryGetBool(B)) { Text = B ? TEXT("True") : TEXT("False"); }
				else { Err = FString::Printf(TEXT("%s.%s: value must be a string, number or bool"), *Obj->GetClass()->GetName(), *KV.Key); return false; }
			}
			if (!P->ImportText_Direct(*Text, P->ContainerPtrToValuePtr<uint8>(Obj), Obj, PPF_None))
			{
				Err = FString::Printf(TEXT("%s.%s: cannot import '%s'"), *Obj->GetClass()->GetName(), *KV.Key, *Text);
				return false;
			}
		}
		return true;
	}

	UClass* NodeClass(const FString& Type)
	{
		if (Type == TEXT("Selector")) return UBTComposite_Selector::StaticClass();
		if (Type == TEXT("Sequence")) return UBTComposite_Sequence::StaticClass();
		return LoadClassPath(Type);
	}

	UBTNode* MakeNode(UBehaviorTree* Tree, const TSharedPtr<FJsonObject>& J, UClass* Required, FString& Err)
	{
		FString Type;
		if (!J.IsValid() || !J->TryGetStringField(TEXT("type"), Type))
		{
			Err = TEXT("node without a type");
			return nullptr;
		}
		UClass* C = NodeClass(Type);
		if (!C || !C->IsChildOf(Required) || C->HasAnyClassFlags(CLASS_Abstract))
		{
			Err = FString::Printf(TEXT("type %s is not a concrete %s"), *Type, *Required->GetName());
			return nullptr;
		}
		UBTNode* N = NewObject<UBTNode>(Tree, C, MakeUniqueObjectName(Tree, C), RF_Transactional);
		FString Name;
		if (J->TryGetStringField(TEXT("name"), Name))
		{
			N->NodeName = Name;
		}
		const TSharedPtr<FJsonObject>* Props = nullptr;
		if (J->TryGetObjectField(TEXT("props"), Props) && !ApplyProps(N, *Props, Err))
		{
			return nullptr;
		}
		return N;
	}

	bool AddServices(UBehaviorTree* Tree, const TSharedPtr<FJsonObject>& J, TArray<TObjectPtr<UBTService>>& Out, FString& Err)
	{
		const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
		if (!J->TryGetArrayField(TEXT("services"), List))
		{
			return true;
		}
		for (const TSharedPtr<FJsonValue>& V : *List)
		{
			UBTNode* S = MakeNode(Tree, V->AsObject(), UBTService::StaticClass(), Err);
			if (!S) return false;
			Out.Add(CastChecked<UBTService>(S));
		}
		return true;
	}

	bool AddDecorators(UBehaviorTree* Tree, const TSharedPtr<FJsonObject>& J, TArray<TObjectPtr<UBTDecorator>>& Out, FString& Err)
	{
		const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
		if (!J->TryGetArrayField(TEXT("decorators"), List))
		{
			return true;
		}
		for (const TSharedPtr<FJsonValue>& V : *List)
		{
			UBTNode* D = MakeNode(Tree, V->AsObject(), UBTDecorator::StaticClass(), Err);
			if (!D) return false;
			Out.Add(CastChecked<UBTDecorator>(D));
		}
		return true;
	}

	UBTCompositeNode* BuildComposite(UBehaviorTree* Tree, const TSharedPtr<FJsonObject>& J, FString& Err)
	{
		UBTNode* N = MakeNode(Tree, J, UBTCompositeNode::StaticClass(), Err);
		if (!N) return nullptr;
		UBTCompositeNode* Comp = CastChecked<UBTCompositeNode>(N);
		if (!AddServices(Tree, J, Comp->Services, Err)) return nullptr;
		const TArray<TSharedPtr<FJsonValue>>* Children = nullptr;
		if (J->TryGetArrayField(TEXT("children"), Children))
		{
			for (const TSharedPtr<FJsonValue>& V : *Children)
			{
				const TSharedPtr<FJsonObject> CJ = V->AsObject();
				FString Type;
				CJ->TryGetStringField(TEXT("type"), Type);
				UClass* C = NodeClass(Type);
				FBTCompositeChild Link;
				if (C && C->IsChildOf(UBTCompositeNode::StaticClass()))
				{
					Link.ChildComposite = BuildComposite(Tree, CJ, Err);
					if (!Link.ChildComposite) return nullptr;
				}
				else
				{
					UBTNode* T = MakeNode(Tree, CJ, UBTTaskNode::StaticClass(), Err);
					if (!T) return nullptr;
					Link.ChildTask = CastChecked<UBTTaskNode>(T);
					if (!AddServices(Tree, CJ, Link.ChildTask->Services, Err)) return nullptr;
				}
				if (!AddDecorators(Tree, CJ, Link.Decorators, Err)) return nullptr;
				Comp->Children.Add(Link);
			}
		}
		return Comp;
	}

	FString NonDefaultProps(UObject* O)
	{
		TArray<FString> L;
		UObject* CDO = O->GetClass()->GetDefaultObject();
		for (TFieldIterator<FProperty> It(O->GetClass()); It; ++It)
		{
			FProperty* P = *It;
			if (P->GetOwnerClass() == UBTNode::StaticClass() || P->GetOwnerClass() == UObject::StaticClass())
			{
				continue;
			}
			const void* V = P->ContainerPtrToValuePtr<void>(O);
			if (P->Identical(V, P->ContainerPtrToValuePtr<void>(CDO)))
			{
				continue;
			}
			FString T;
			P->ExportTextItem_Direct(T, V, nullptr, O, PPF_None);
			L.Add(FString::Printf(TEXT("%s=%s"), *P->GetName(), *T));
		}
		return FString::Join(L, TEXT(", "));
	}

	void Describe(UBTNode* N, int32 Depth, TArray<FString>& Out)
	{
		const FString Pad = FString::ChrN(Depth * 2, TEXT(' '));
		Out.Add(FString::Printf(TEXT("%s%s \"%s\" {%s}"), *Pad, *N->GetClass()->GetName(), *N->NodeName, *NonDefaultProps(N)));
		auto Services = [&](const TArray<TObjectPtr<UBTService>>& S) {
			for (UBTService* X : S)
			{
				Out.Add(FString::Printf(TEXT("%s  service %s {%s}"), *Pad, *X->GetClass()->GetName(), *NonDefaultProps(X)));
			}
		};
		if (UBTCompositeNode* C = Cast<UBTCompositeNode>(N))
		{
			Services(C->Services);
			for (const FBTCompositeChild& Ch : C->Children)
			{
				for (UBTDecorator* D : Ch.Decorators)
				{
					Out.Add(FString::Printf(TEXT("%s  @ %s {%s}"), *Pad, *D->GetClass()->GetName(), *NonDefaultProps(D)));
				}
				if (Ch.ChildComposite) Describe(Ch.ChildComposite, Depth + 1, Out);
				if (Ch.ChildTask) Describe(Ch.ChildTask, Depth + 1, Out);
			}
		}
		else if (UBTTaskNode* T = Cast<UBTTaskNode>(N))
		{
			Services(T->Services);
		}
	}
}

UBehaviorTree* UBotsCoordGraphLibrary::CreateOrLoadBehaviorTree(const FString& AssetPath)
{
	const FString AssetName = FPackageName::GetLongPackageAssetName(AssetPath);
	UBehaviorTree* Tree = LoadObject<UBehaviorTree>(nullptr, *(AssetPath + TEXT(".") + AssetName), nullptr, LOAD_NoWarn | LOAD_Quiet);
	if (!Tree)
	{
		UPackage* Pkg = CreatePackage(*AssetPath);
		Tree = NewObject<UBehaviorTree>(Pkg, FName(*AssetName), RF_Public | RF_Standalone | RF_Transactional);
		FAssetRegistryModule::AssetCreated(Tree);
	}
	Tree->MarkPackageDirty();
	Ok();
	return Tree;
}

bool UBotsCoordGraphLibrary::BuildBehaviorTree(UBehaviorTree* Tree, const FString& JsonSpec)
{
	if (!Tree) return FailB(TEXT("BuildBehaviorTree: no tree"));
	TSharedPtr<FJsonObject> J;
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(JsonSpec), J) || !J.IsValid())
	{
		return FailB(TEXT("BuildBehaviorTree: spec is not valid JSON"));
	}
	// old runtime nodes and the editor graph leave the package (they would otherwise be saved as orphans)
	TArray<UObject*> Inner;
	GetObjectsWithOuter(Tree, Inner, false);
	for (UObject* O : Inner)
	{
		if (O->IsA<UBTNode>() || O->IsA<UEdGraph>())
		{
			O->ClearFlags(RF_Public | RF_Standalone);
			O->Rename(nullptr, GetTransientPackage(), REN_DontCreateRedirectors | REN_NonTransactional);
		}
	}
#if WITH_EDITORONLY_DATA
	Tree->BTGraph = nullptr;
#endif
	Tree->RootNode = nullptr;
	Tree->RootDecorators.Reset();
	FString BB;
	Tree->BlackboardAsset = nullptr;
	if (J->TryGetStringField(TEXT("blackboard"), BB) && !BB.IsEmpty())
	{
		Tree->BlackboardAsset = LoadObject<UBlackboardData>(nullptr, *BB);
		if (!Tree->BlackboardAsset) return FailB(FString::Printf(TEXT("blackboard %s not found"), *BB));
	}
	FString Err;
	const TSharedPtr<FJsonObject>* Root = nullptr;
	if (!J->TryGetObjectField(TEXT("root"), Root)) return FailB(TEXT("spec has no root"));
	Tree->RootNode = BuildComposite(Tree, *Root, Err);
	if (!Tree->RootNode) return FailB(Err);
	if (!AddDecorators(Tree, J, Tree->RootDecorators, Err)) return FailB(Err);
	Tree->MarkPackageDirty();
	Ok();
	return true;
}

FString UBotsCoordGraphLibrary::DescribeBehaviorTree(UBehaviorTree* Tree)
{
	if (!Tree || !Tree->RootNode) return TEXT("(empty)");
	TArray<FString> Out;
	Out.Add(FString::Printf(TEXT("tree %s blackboard %s"), *Tree->GetPathName(), *GetPathNameSafe(Tree->BlackboardAsset)));
	for (UBTDecorator* D : Tree->RootDecorators)
	{
		Out.Add(FString::Printf(TEXT("@root %s {%s}"), *D->GetClass()->GetName(), *NonDefaultProps(D)));
	}
	Describe(Tree->RootNode, 0, Out);
	return FString::Join(Out, TEXT("\n"));
}
