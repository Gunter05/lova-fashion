export const translations = {
  en: {
    common: {
      user: 'User',
      loading: 'Loading...',
      saving: 'Saving...',
      error: 'Error',
      success: 'Success',
      continue: 'Continue',
      close: 'Close',
      active: 'active',
      start: 'Start',
      or: 'or'
    },
    auth: {
      welcome: 'Welcome to',
      loginTitle: 'LOVA FASHION',
      loginSubtitle: 'Log in to continue',
      email: 'Email address',
      password: 'Password',
      rememberMe: 'Remember me',
      forgotPassword: 'Forgot password?',
      loginBtn: 'Log In',
      loggingIn: 'Logging in...',
      createAccount: 'Create an account',
      joinTitle: 'Create an account',
      joinSubtitle: 'Join LOVA FASHION',
      fullName: 'Full name',
      registerBtn: 'Create my account',
      registering: 'Creating...',
      alreadyHaveAccount: 'Already have an account? Log In',
      legalText: 'By continuing, you accept our {terms} and our {privacy}',
      terms: 'Terms of Use',
      privacy: 'Privacy Policy',
      regSuccess: 'Account successfully created. You can now log in.',
      defaultError: 'Invalid credentials. Please try again.'
    },
    nav: {
      measurements: 'Measurements',
      catalog: 'Catalog',
      reports: 'Reports',
      profile: 'My Profile',
      journey: {
        measurements: 'Measurements',
        catalog: 'Catalog',
        ease: 'Ease',
        compat: 'Compat.',
        report: 'Report',
        completed: 'Step {n}: {label} (completed)',
        inProgress: 'Step {n}: {label} (in progress)'
      }
    },
    profile: {
      changePhoto: 'Change photo',
      edit: 'Edit',
      unableLoad: 'Unable to load profile.',
      updated: 'Profile updated successfully.',
      photoUpdated: 'Profile photo updated.',
      uploadFailed: 'Upload failed.',
      personalInfo: 'Personal Information',
      role: 'Role',
      regDate: 'Registration date',
      fullName: 'Full name',
      email: 'Email address',
      saveBtn: 'Save',
      savingBtn: 'Saving...',
      photoHistory: 'Photo history',
      roles: {
        Client: 'Client',
        Tailor: 'Tailor',
        Admin: 'Administrator'
      }
    },
    measurements: {
      title: 'My Measurement Workshop',
      subtitle: 'For accurate measurements, follow these tips.',
      tips: {
        straight: {
          title: 'Stand straight',
          desc: 'Keep your back straight and shoulders relaxed.'
        },
        fitting: {
          title: 'Wear form-fitting clothes',
          desc: 'Avoid loose or thick clothing.'
        },
        waist: {
          title: 'Place phone at waist level',
          desc: 'Ask someone to help you.'
        }
      },
      btnStart: 'Start',
      captureSessions: 'Capture sessions',
      sessionDetail: 'Session detail',
      analyzing: 'Analyzing...',
      instructions: 'Upload your two photos (front & side), then enter your height.',
      failureReason: 'Reason for failure:',
      frontPhoto: 'Front photo',
      sidePhoto: 'Side photo',
      height: 'Height (cm)',
      processBtn: 'Process',
      processingBtn: 'Processing...',
      chooseFabricPattern: 'Choose my fabric and pattern →',
      estimatedMeasurements: 'Your estimated measurements',
      chest: 'Chest circumference',
      waist: 'Waist circumference',
      hips: 'Hips circumference',
      arm: 'Arm length',
      noSessions: 'No sessions. Click "Start" to begin.',
      newSessionCreated: 'New session created.',
      frontPhotoUploaded: 'Front photo uploaded.',
      sidePhotoUploaded: 'Side photo uploaded.',
      processingStarted: 'Processing started.',
      statureError: 'Please enter a valid height (100–250 cm).',
      unableLoadSessions: 'Unable to load sessions.'
    },
    catalog: {
      title: 'Choose your pattern',
      subtitle: 'and your fabric',
      tabs: {
        patterns: 'PATTERNS',
        fabrics: 'FABRICS'
      },
      selected: {
        fabric: 'Fabric:',
        pattern: 'Pattern:',
        calculateEase: 'Calculate ease →'
      },
      filters: {
        all: 'All'
      },
      searchFabric: 'Search fabric...',
      searchPattern: 'Search pattern...',
      noFabricFound: 'No fabric found.',
      noPatternFound: 'No pattern found.',
      fabricCard: {
        soft: 'Soft',
        chooseBtn: 'Choose this fabric'
      },
      fabricDetail: {
        composition: 'Composition',
        elasticity: 'Elasticity',
        weight: 'Weight',
        price: 'Price',
        chooseBtn: 'Choose this fabric',
        descPlaceholder: 'Soft and bright fabric with a beautiful fluid drape.'
      },
      modelCard: {
        viewBtn: 'View pattern'
      },
      modelDetail: {
        recommendedShapes: 'Recommended body shapes',
        compatibleFabrics: 'Compatible fabrics',
        chooseBtn: 'Choose this pattern ✓',
        unableLoad: 'Unable to load pattern details.'
      },
      errors: {
        unableLoadFabrics: 'Unable to load fabrics.',
        unableLoadModels: 'Unable to load patterns.',
        filterError: 'Error filtering fabrics.',
        unavailableFabric: 'Fabric unavailable.'
      }
    },
    ease: {
      title: 'Ease Margins',
      subtitle: 'Calculate adjustments according to the selected fabric.',
      selectedFabric: 'Selected fabric:',
      pattern: 'Pattern:',
      alreadyCalculated: 'Adjustment already calculated.',
      compatibilityBtn: 'Compatibility →',
      newCalculation: 'New calculation',
      measureSession: 'Measurement session',
      noValidatedSession: 'No validated session.',
      completeMeasurements: 'Complete measurements',
      chooseSession: 'Choose a session...',
      sessionOf: 'Session of {date}',
      fabricLabel: 'Fabric',
      chooseFabric: 'Choose a fabric...',
      calculating: 'Calculating...',
      calculateEaseBtn: 'Calculate ease',
      verifyCompatibilityBtn: 'Verify compatibility →',
      adjustmentHistory: 'Adjustment history',
      noAdjustments: 'No adjustments for this session.',
      resultTitle: 'Result — {fabric}',
      chest: 'Chest',
      waist: 'Waist',
      hips: 'Hips',
      easeLabel: 'ease',
      ruleSource: 'Rule source:',
      useBtn: 'Use',
      successMessage: 'Adjustment successfully calculated.',
      selectedMessage: 'Adjustment selected.',
      unableLoadData: 'Unable to load necessary data.'
    },
    compatibility: {
      title: 'Compatibility',
      subtitle: 'Verify fabric / pattern / body shape compatibility.',
      selection: 'Selection',
      measureSession: 'Measurement session',
      noValidatedSession: 'No validated session.',
      completeMeasurements: 'Complete measurements',
      chooseSession: 'Choose a session...',
      adjustmentLabel: 'Adjustment (fabric + ease)',
      noAdjustment: 'No adjustment.',
      calculateEaseBtn: 'Calculate ease margins',
      chooseAdjustment: 'Choose an adjustment...',
      patternLabel: 'Pattern',
      noPatternAvailable: 'No pattern available.',
      choosePatternBtn: 'Choose a pattern',
      choosePatternOption: 'Choose a pattern...',
      verifying: 'Verifying...',
      checkBtn: 'Check compatibility',
      verdicts: {
        compatible: 'Compatible ✓',
        partially_compatible: 'Partially compatible',
        incompatible: 'Incompatible ✗',
        excellent: 'Excellent choice!'
      },
      gaugeLabel: 'Compatibility',
      watchZones: 'Areas to watch',
      seeSummaryBtn: 'See my summary →',
      unableLoadData: 'Unable to load data.'
    },
    report: {
      bannerSubtitle: 'Module 7',
      bannerTitle: 'Your custom outfit',
      bannerTitleStyled: 'tailored to fit',
      bannerDesc: 'Complete summary of your measurements, fabric, and pattern.',
      noReportTitle: 'No reports available',
      noReportDesc: 'Complete the steps to generate your first style book.',
      guide: {
        measurements: 'Take your measurements',
        catalog: 'Choose fabric & pattern',
        ease: 'Calculate ease margins',
        compat: 'Verify compatibility'
      },
      reportCode: 'Report #{code}...',
      summary: 'Summary',
      customOutfit: 'Your custom outfit',
      adjustedMeasurements: 'Adjusted measurements',
      chest: 'Chest circumference',
      waist: 'Waist circumference',
      hips: 'Hips circumference',
      elasticity: 'Elasticity',
      recommendations: 'Recommendations',
      sendBtn: 'Send to the tailoring workshop →',
      onlyClientsError: 'Only clients can view their reports here.',
      unableLoadReports: 'Unable to load reports.',
      unableLoadReportDetail: 'Unable to load report.',
      fabricId: 'Fabric ID:',
      patternId: 'Pattern ID:',
      adjustmentId: 'Adjustment ID:'
    },
    types: {
      Tous: 'All',
      Robe: 'Dress',
      Chemise: 'Shirt',
      Pantalon: 'Trousers',
      Jupe: 'Skirt',
      Veste: 'Jacket',
      Manteau: 'Coat',
      Costume: 'Suit'
    }
  },
  fr: {
    common: {
      user: 'Utilisateur',
      loading: 'Chargement...',
      saving: 'Enregistrement...',
      error: 'Erreur',
      success: 'Succès',
      continue: 'Continuer',
      close: 'Fermer',
      active: 'active',
      start: 'Commencer',
      or: 'ou'
    },
    auth: {
      welcome: 'Bienvenue chez',
      loginTitle: 'LOVA FASHION',
      loginSubtitle: 'Connectez-vous pour continuer',
      email: 'Adresse e-mail',
      password: 'Mot de passe',
      rememberMe: 'Se souvenir de moi',
      forgotPassword: 'Mot de passe oublié ?',
      loginBtn: 'Se connecter',
      loggingIn: 'Connexion en cours...',
      createAccount: 'Créer un compte',
      joinTitle: 'Créer un compte',
      joinSubtitle: 'Rejoignez LOVA FASHION',
      fullName: 'Nom complet',
      registerBtn: 'Créer mon compte',
      registering: 'Création en cours...',
      alreadyHaveAccount: 'Déjà un compte ? Se connecter',
      legalText: 'En continuant, vous acceptez nos {terms} et notre {privacy}',
      terms: "Conditions d'utilisation",
      privacy: 'Politique de confidentialité',
      regSuccess: 'Compte créé avec succès. Vous pouvez maintenant vous connecter.',
      defaultError: 'Identifiants incorrects. Veuillez réessayer.'
    },
    nav: {
      measurements: 'Mesures',
      catalog: 'Catalogue',
      reports: 'Rapports',
      profile: 'Mon Profil',
      journey: {
        measurements: 'Mesures',
        catalog: 'Catalogue',
        ease: 'Aisance',
        compat: 'Compat.',
        report: 'Rapport',
        completed: 'Étape {n} : {label} (complétée)',
        inProgress: 'Étape {n} : {label} (en cours)'
      }
    },
    profile: {
      changePhoto: 'Changer la photo',
      edit: 'Modifier',
      unableLoad: 'Impossible de charger le profil.',
      updated: 'Profil mis à jour avec succès.',
      photoUpdated: 'Photo de profil mise à jour.',
      uploadFailed: 'Échec du téléversement.',
      personalInfo: 'Informations personnelles',
      role: 'Rôle',
      regDate: "Date d'inscription",
      fullName: 'Nom complet',
      email: 'Adresse e-mail',
      saveBtn: 'Enregistrer',
      savingBtn: 'Enregistrement...',
      photoHistory: 'Historique des photos',
      roles: {
        Client: 'Client',
        Tailor: 'Tailleur',
        Admin: 'Administrateur'
      }
    },
    measurements: {
      title: 'Mon Atelier de mesures',
      subtitle: 'Pour des mesures précises, suivez ces conseils.',
      tips: {
        straight: {
          title: 'Tenez-vous droit',
          desc: 'Gardez le dos droit et les épaules relâchées.'
        },
        fitting: {
          title: 'Portez des vêtements près du corps',
          desc: 'Évitez les vêtements amples ou épais.'
        },
        waist: {
          title: 'Posez le téléphone au niveau de la taille',
          desc: "Demandez à quelqu'un de vous aider."
        }
      },
      btnStart: 'Commencer',
      captureSessions: 'Sessions de capture',
      sessionDetail: 'Détail de la session',
      analyzing: 'Analyse en cours...',
      instructions: 'Téléversez vos deux photos (face & profil), puis renseignez votre stature.',
      failureReason: "Motif d'échec :",
      frontPhoto: 'Photo face',
      sidePhoto: 'Photo profil',
      height: 'Stature (cm)',
      processBtn: 'Lancer',
      processingBtn: 'Lancement...',
      chooseFabricPattern: 'Choisir mon tissu et patron →',
      estimatedMeasurements: 'Vos mesures estimées',
      chest: 'Tour de poitrine',
      waist: 'Tour de taille',
      hips: 'Tour de hanches',
      arm: 'Longueur de bras',
      noSessions: 'Aucune session. Appuyez sur "Commencer" pour débuter.',
      newSessionCreated: 'Nouvelle session créée.',
      frontPhotoUploaded: 'Photo face téléversée.',
      sidePhotoUploaded: 'Photo profil téléversée.',
      processingStarted: 'Traitement lancé.',
      statureError: 'Veuillez saisir une stature valide (100–250 cm).',
      unableLoadSessions: 'Impossible de charger les sessions.'
    },
    catalog: {
      title: 'Choisissez votre modèle',
      subtitle: 'et votre tissu',
      tabs: {
        patterns: 'MODÈLES',
        fabrics: 'TISSUS'
      },
      selected: {
        fabric: 'Tissu :',
        pattern: 'Patron :',
        calculateEase: "Calculer l'aisance →"
      },
      filters: {
        all: 'Tous'
      },
      searchFabric: 'Rechercher un tissu…',
      searchPattern: 'Rechercher un modèle…',
      noFabricFound: 'Aucun tissu trouvé.',
      noPatternFound: 'Aucun modèle trouvé.',
      fabricCard: {
        soft: 'Souple',
        chooseBtn: 'Choisir ce tissu'
      },
      fabricDetail: {
        composition: 'Composition',
        elasticity: 'Élasticité',
        weight: 'Poids',
        price: 'Prix',
        chooseBtn: 'Choisir ce tissu',
        descPlaceholder: 'Tissu doux et lumineux avec un beau tombé fluide.'
      },
      modelCard: {
        viewBtn: 'Voir le modèle'
      },
      modelDetail: {
        recommendedShapes: 'Morphologies recommandées',
        compatibleFabrics: 'Tissus compatibles',
        chooseBtn: 'Choisir ce patron ✓',
        unableLoad: 'Impossible de charger les détails du patron.'
      },
      errors: {
        unableLoadFabrics: 'Impossible de charger les tissus.',
        unableLoadModels: 'Impossible de charger les modèles.',
        filterError: 'Erreur lors du filtrage.',
        unavailableFabric: 'Tissu indisponible.'
      }
    },
    ease: {
      title: "Marges d'Aisance",
      subtitle: 'Calculez les ajustements selon le tissu sélectionné.',
      selectedFabric: 'Tissu retenu :',
      pattern: 'Patron :',
      alreadyCalculated: 'Ajustement déjà calculé.',
      compatibilityBtn: 'Compatibilité →',
      newCalculation: 'Nouveau calcul',
      measureSession: 'Session de mesures',
      noValidatedSession: 'Aucune session validée.',
      completeMeasurements: 'Compléter les mesures',
      chooseSession: 'Choisir une session…',
      sessionOf: 'Session du {date}',
      fabricLabel: 'Tissu',
      chooseFabric: 'Choisir un tissu…',
      calculating: 'Calcul en cours…',
      calculateEaseBtn: "Calculer l'aisance",
      verifyCompatibilityBtn: 'Vérifier la compatibilité →',
      adjustmentHistory: 'Historique des ajustements',
      noAdjustments: 'Aucun ajustement pour cette session.',
      resultTitle: 'Résultat — {fabric}',
      chest: 'Poitrine',
      waist: 'Taille',
      hips: 'Hanches',
      easeLabel: 'aisance',
      ruleSource: 'Source règles :',
      useBtn: 'Utiliser',
      successMessage: 'Ajustement calculé avec succès.',
      selectedMessage: 'Ajustement sélectionné.',
      unableLoadData: 'Impossible de charger les données nécessaires.'
    },
    compatibility: {
      title: 'Compatibilité',
      subtitle: 'Vérifiez la compatibilité tissu / patron / morphologie.',
      selection: 'Sélection',
      measureSession: 'Session de mesures',
      noValidatedSession: 'Aucune session validée.',
      completeMeasurements: 'Compléter les mesures',
      chooseSession: 'Choisir une session…',
      adjustmentLabel: 'Ajustement (tissu + aisance)',
      noAdjustment: 'Aucun ajustement.',
      calculateEaseBtn: "Calculer les marges d'aisance",
      chooseAdjustment: 'Choisir un ajustement…',
      patternLabel: 'Patron',
      noPatternAvailable: 'Aucun patron disponible.',
      choosePatternBtn: 'Choisir un patron',
      choosePatternOption: 'Choisir un patron…',
      verifying: 'Vérification…',
      checkBtn: 'Voir la compatibilité',
      verdicts: {
        compatible: 'Compatible ✓',
        partially_compatible: 'Partiellement compatible',
        incompatible: 'Incompatible ✗',
        excellent: 'Excellent choix !'
      },
      gaugeLabel: 'Compatibilité',
      watchZones: 'Zones à surveiller',
      seeSummaryBtn: 'Voir mon récapitulatif →',
      unableLoadData: 'Impossible de charger les données.'
    },
    report: {
      bannerSubtitle: 'Module 7',
      bannerTitle: 'Votre vêtement',
      bannerTitleStyled: 'taillé sur mesure',
      bannerDesc: 'Synthèse complète de vos mesures, tissu et patron.',
      noReportTitle: 'Aucun rapport disponible',
      noReportDesc: 'Complétez les étapes du parcours pour générer votre premier carnet de style.',
      guide: {
        measurements: 'Prenez vos mesures',
        catalog: 'Choisissez tissu & patron',
        ease: "Calculez les marges d'aisance",
        compat: 'Vérifiez la compatibilité'
      },
      reportCode: 'Rapport #{code}...',
      summary: 'Récapitulatif',
      customOutfit: 'Votre tenue sur mesure',
      adjustedMeasurements: 'Mesures ajustées',
      chest: 'Tour de poitrine',
      waist: 'Tour de taille',
      hips: 'Tour de hanches',
      elasticity: 'Élasticité',
      recommendations: 'Recommandations',
      sendBtn: "Envoyer à l'atelier de confection →",
      onlyClientsError: 'Seuls les clients peuvent consulter leurs rapports ici.',
      unableLoadReports: 'Impossible de charger les rapports.',
      unableLoadReportDetail: 'Impossible de charger le rapport.',
      fabricId: 'Tissu ID :',
      patternId: 'Patron ID :',
      adjustmentId: 'Ajustement ID :'
    },
    types: {
      Tous: 'Tous',
      Robe: 'Robe',
      Chemise: 'Chemise',
      Pantalon: 'Pantalon',
      Jupe: 'Jupe',
      Veste: 'Veste',
      Manteau: 'Manteau',
      Costume: 'Costume'
    }
  }
};
